import json
import re
import os
import logging
import threading

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

_model = None
_tokenizer = None
_load_lock = threading.Lock()


def _load_model():
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    with _load_lock:
        if _model is not None:
            return _model, _tokenizer

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
        except ImportError:
            raise ImportError(
                "Missing dependencies. Run: pip install transformers torch accelerate"
            )

        logger.info("Loading model %s ...", MODEL_ID)
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        logger.info("Device: %s", device.upper())

        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        _model.eval()
        logger.info("Model ready.")
        return _model, _tokenizer


SYSTEM_PROMPT = (
    "You are a B2B sales intelligence analyst.\n\n"
    "Analyze the company information provided and return ONLY a JSON object.\n"
    "No markdown, no explanation, no text outside the JSON.\n\n"
    "JSON format:\n"
    "{\n"
    '  "company_overview": "2-3 sentences describing what the company does",\n'
    '  "core_product": "primary product or service offered",\n'
    '  "target_customer": "who their customers are",\n'
    '  "b2b_qualified": "Yes",\n'
    '  "b2b_reasoning": "reason for the qualification decision",\n'
    '  "sales_questions": ["question 1", "question 2", "question 3"]\n'
    "}\n\n"
    "b2b_qualified values:\n"
    '- "Yes": company sells to other businesses or operates at commercial scale\n'
    '- "No": company serves only individual consumers\n'
    '- "Uncertain": genuinely cannot determine from available information\n\n'
    "Return only the JSON object."
)


def _build_prompt(lead, scraped):
    lines = ["Lead: " + lead]
    if scraped.get("url"):
        lines.append("URL: " + scraped["url"])
    content = scraped.get("content", "").strip()
    if content:
        lines.append("\nWebsite content:\n" + content[:2000])
    else:
        lines.append("\nNo website content available. Use the company name to infer industry and likely customers.")
    return "\n".join(lines)


def _parse_response(text):
    if not text or not text.strip():
        return None

    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _normalize_b2b(value):
    v = (value or "").strip().lower()
    if v == "yes":
        return "Yes"
    if v == "no":
        return "No"
    return "Uncertain"


def _run_inference(prompt_text):
    model, tokenizer = _load_model()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        prompt = "System: " + SYSTEM_PROMPT + "\n\nUser: " + prompt_text + "\n\nAssistant:"

    import torch
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def analyze_lead(lead, scraped):
    prompt_text = _build_prompt(lead, scraped)

    logger.info("Analyzing: %s", lead)
    raw = _run_inference(prompt_text)
    logger.info("Raw output: %s", repr(raw[:200]))

    parsed = _parse_response(raw)

    base = {
        "lead": lead,
        "url": scraped.get("url", ""),
        "source_type": scraped.get("source_type", "unknown"),
        "scraped_success": scraped.get("success", False),
    }

    if parsed is None:
        return {
            **base,
            "company_overview": "Could not parse model output.",
            "core_product": "-",
            "target_customer": "-",
            "b2b_qualified": "Uncertain",
            "b2b_reasoning": "Model response was not valid JSON.",
            "sales_questions": [],
        }

    parsed["b2b_qualified"] = _normalize_b2b(parsed.get("b2b_qualified", ""))
    return {**base, **parsed}
