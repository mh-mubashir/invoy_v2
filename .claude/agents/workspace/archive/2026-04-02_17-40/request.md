# Request: Add InternVL2-2B and InternVL2-4B as selectable vision models

## Background

Invoy currently supports Qwen2-VL 2B and Qwen2.5-VL 3B. The 2B model has been producing
hallucinated/example-copied output. We want to add InternVL2 (2B and 4B) as alternative
backends to test for better screenshot understanding.

## What to build

### 1. New `InternVL2Backend` in `invoy_sdk/vlm_backends.py`

Add a new class `InternVL2Backend(VLMBackend)` alongside the existing `Qwen2VLBackend`.

InternVL2 has a completely different inference stack from Qwen2-VL:

**Model loading:**
```python
from transformers import AutoModel, AutoTokenizer
model = AutoModel.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True,
    trust_remote_code=True,
    device_map="auto",   # for GPU; omit for CPU then call .to(device)
).eval()
tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True, use_fast=False)
```

**Image preprocessing** (InternVL2 does NOT use AutoProcessor — requires custom transform):
```python
from torchvision import transforms as T
from torchvision.transforms.functional import InterpolationMode

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD  = (0.229, 0.224, 0.225)

transform = T.Compose([
    T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
    T.Resize((448, 448), interpolation=InterpolationMode.BICUBIC),
    T.ToTensor(),
    T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])
pixel_values = transform(Image.open(image_path)).unsqueeze(0)  # (1,3,448,448)
pixel_values = pixel_values.to(torch.bfloat16).to(device)
```

**Inference:**
```python
generation_config = dict(max_new_tokens=max_new_tokens, do_sample=False)
question = f"<image>\n{prompt}"
response = model.chat(tokenizer, pixel_values, question, generation_config)
# response is a plain string — no decode step needed
```

**`log_model_name`** must return `f"internvl2:{self.model_id}"`.

**`generate()` signature** must match `VLMBackend.generate()` exactly:
- `prompt: str`, `image_paths: list[str]`, `max_new_tokens: int`, `use_extractor_model: bool = False`
- Returns `tuple[Optional[str], float]` — (response_text, wall_time_ms)
- Use only the FIRST image path (same as Qwen backend does)
- Return `(None, 0.0)` if model not loaded or an exception occurs (print the error)

**Helper function** `_is_internvl2_model_id(model_id: str) -> bool`:
```python
def _is_internvl2_model_id(model_id: str) -> bool:
    return "internvl" in model_id.lower()
```

### 2. Update `invoy_app/settings/config.py`

In `AVAILABLE_MODELS`, add two new entries:
```python
AVAILABLE_MODELS: dict[str, str] = {
    "Qwen2-VL 2B":    "Qwen/Qwen2-VL-2B-Instruct",
    "Qwen2.5-VL 3B":  "Qwen/Qwen2.5-VL-3B-Instruct",
    "InternVL2 2B":   "OpenGVLab/InternVL2-2B",
    "InternVL2 4B":   "OpenGVLab/InternVL2-4B",
}
```

No other changes to config.py.

### 3. Update `invoy_app/core/recorder.py`

In `_load_model_then_capture`, the recorder currently always creates a `Qwen2VLBackend`.
It must now detect which backend to use based on `self._config.model_id`:

```python
from invoy_sdk.vlm_backends import Qwen2VLBackend, InternVL2Backend, _is_internvl2_model_id

def _load_model_then_capture(self) -> None:
    print(f"[Invoy] Loading model {self._config.model_id}…")
    try:
        if _is_internvl2_model_id(self._config.model_id):
            self._backend = InternVL2Backend(
                model_id=self._config.model_id,
                device=self._config.device,
            )
        else:
            self._backend = Qwen2VLBackend(
                model_id=self._config.model_id,
                device=self._config.device,
            )
        self._backend._ensure_loaded()
    ...
```

The type annotation on `self._backend` must be widened to `Optional[VLMBackend]`
(import `VLMBackend` from `invoy_sdk.vlm_backends`).

### 4. Update `invoy_app/app.py`

In `_short_model_label()`, add InternVL2 labels:
```python
def _short_model_label(self) -> str:
    mid = self._config.model_id
    if "InternVL2-4B" in mid or "InternVL2_4B" in mid:
        return "InternVL2 4B"
    if "InternVL2-2B" in mid or "InternVL2_2B" in mid:
        return "InternVL2 2B"
    if "3B" in mid:
        return "Qwen2.5-VL 3B"
    if "2B" in mid:
        return "Qwen2-VL 2B"
    if "7B" in mid:
        return "Qwen2-VL 7B"
    return mid.split("/")[-1][:20]
```

## Files to change

1. `invoy_sdk/vlm_backends.py`
2. `invoy_app/settings/config.py`
3. `invoy_app/core/recorder.py`
4. `invoy_app/app.py`

## Out of scope

- Do NOT change `ACTIVITY_PROMPT` or `CHANGE_PROMPT_TMPL`
- Do NOT change `settings_window.py` — it already reads `AVAILABLE_MODELS` dynamically
- Do NOT add `torchvision` to requirements — it is already installed as a torch dependency
- Do NOT change `app.py` beyond `_short_model_label()`

## Success criteria

1. Settings window shows four model options: Qwen2-VL 2B, Qwen2.5-VL 3B, InternVL2 2B, InternVL2 4B
2. Selecting InternVL2 2B or 4B and saving config causes recorder to load `InternVL2Backend`
3. Selecting a Qwen model still loads `Qwen2VLBackend` — no regression
4. `InternVL2Backend.generate()` returns a plain string response, not token IDs
5. The model label in the UI shows "InternVL2 2B" or "InternVL2 4B" correctly
