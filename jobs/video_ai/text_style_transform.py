import argparse

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


DEFAULT_MODEL = "google/flan-t5-base"


def fallback_rewrite(text: str, style: str) -> str:
    clean = " ".join(text.split())
    s = style.strip().lower()
    if s == "confident":
        clean = clean.replace("I think", "I am confident").replace("maybe", "").replace("probably", "")
        return f"{clean.strip()}."
    if s == "shaky":
        return f"Um, {clean}... I think."
    if s == "persuasive":
        return f"{clean} This is the right move, and we should do it now."
    if s == "calm":
        return f"{clean} Let's keep this steady and clear."
    return clean


def near_identical(a: str, b: str) -> bool:
    na = " ".join(a.lower().split())
    nb = " ".join(b.lower().split())
    return na == nb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--style", default="confident")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--top-p", type=float, default=0.92)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model)

    prompt = (
        "Rewrite the spoken text so the tone is clearly changed while preserving core meaning. "
        f"Target speaking style: {args.style}. "
        "Use different wording, keep similar length, and output only the rewritten text.\n\n"
        f"Text: {args.text}"
    )
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True)
    outputs = model.generate(
        **inputs,
        max_new_tokens=args.max_new_tokens,
        do_sample=True,
        temperature=args.temperature,
        top_p=args.top_p,
        repetition_penalty=1.1,
    )
    rewritten = tokenizer.decode(outputs[0], skip_special_tokens=True).strip() or args.text.strip()
    if near_identical(rewritten, args.text):
        rewritten = fallback_rewrite(args.text, args.style)
    print(rewritten)


if __name__ == "__main__":
    main()
