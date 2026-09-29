# Unlimited-OCR fact sheet for the Windows desktop OCR app (research state 2026-09-27, fact-checked)

Status tags: **[C]** confirmed in a primary source, **[L]** likely (secondary source or inference), **[U]** unconfirmed, **[FC]** line changed or added by the fact-check round (details in section 11). Target: RTX 4080 SUPER 16 GB, Intel Core Ultra 7 265K, 64 GB RAM, Python 3.11, Flask + pywebview + PyInstaller.

---

## 1 Model & license

**Identity**
- HF repo `baidu/Unlimited-OCR`; paper "Unlimited OCR Works", arXiv 2606.23050, submitted 2026-06-22, 17 Baidu authors (https://arxiv.org/abs/2606.23050, https://arxiv.org/html/2606.23050, https://arxiv.org/html/2606.23050v1). [C]
- Continue-train of DeepSeek-OCR: 4,000 steps, batch 256, lr 1e-4, 8x16 A800 GPUs, 32K max length, DeepEncoder frozen, decoder only. [C]
- Training data: ~2M document OCR samples, 9:1 single:multi-page, single pages annotated with PaddleOCR, ~200k multi-page samples synthesized by concatenating 2–50 pages. Language mix not stated. [C]
- Core change: all decoder attention replaced by Reference Sliding Window Attention (R-SWA). Every token sees the whole prefill plus the last 128 generated tokens; KV cache is constant at Lm + 128. [C]
- Paper §7 limit: "cannot achieve truly unlimited parsing under a finite context length (e.g., 32K), as it is also constrained by the prefill length"; 128K training planned. [C]

**Architecture** (https://huggingface.co/baidu/Unlimited-OCR/raw/main/config.json) [C]
- `architectures ['UnlimitedOCRForCausalLM']`, `model_type 'unlimited-ocr'`, `torch_dtype bfloat16`, `transformers_version 4.46.3`.
- Decoder: DeepseekV2 MoE, 12 layers, hidden 1280, 10 heads / 10 KV heads, v_head_dim 128, intermediate 6848, moe_intermediate 896, 64 routed + 2 shared experts, 6 experts per token, first_k_dense_replace 1, vocab 129280, max_position_embeddings 32768, sliding_window 128, use_mla false.
- Vision `deeplip_b_l`: SAM ViT-B (1024 px, patch 16, 768) + CLIP-L/14-224 (1024), linear projector 2048→1280, 16x token compression.
- `processor_config.json` (https://huggingface.co/baidu/Unlimited-OCR/raw/main/processor_config.json): patch_size 16, downsample_ratio 4, image_mean/std 0.5, candidate_resolutions [[1024,1024]].
- `auto_map`: AutoConfig → `modeling_unlimitedocr.UnlimitedOCRConfig`, AutoModel → `modeling_unlimitedocr.UnlimitedOCRForCausalLM`. Load with `AutoModel`, not `AutoModelForCausalLM`.
- [FC] Why `AutoModel` matters: no class in the remote code inherits `GenerationMixin`. transformers 4.57.1 injects it via `add_generation_mixin_to_remote_model` in auto_factory.py (lines 452, 596, 748). Importing `UnlimitedOCRForCausalLM` directly gives a model without `generate()` (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/models/auto/auto_factory.py). [C]
- Nested `language_config.auto_map` points to `modeling_deepseek.DeepseekV2Model` / `configuration_deepseekv2.DeepseekV2Config`, files that do not exist in the repo. Probably harmless. [U]

**Parameter count**
- Paper: "3B total and 500M activated parameters". HF API safetensors parameters 3,336,106,240 (BF16). Docling lists "3.34B MoE". MORE names the parent "DeepSeekOCR 3B-A570M". [C]
- Conflict: the vLLM recipe labels it "3B · DENSE" (https://recipes.vllm.ai/baidu/Unlimited-OCR). Config and paper say MoE and are better sourced.
- One research angle rated the 3B/500M figure only "likely" (secondary sources); another quotes it from the paper directly. The paper quote wins.

**Files at revision `07dea832e22aefee32ad281d4b80551282e1c168`** (https://huggingface.co/api/models/baidu/Unlimited-OCR?blobs=true, https://huggingface.co/api/models/baidu/Unlimited-OCR/tree/main, https://huggingface.co/api/models/baidu/Unlimited-OCR/tree/main/assets, https://huggingface.co/baidu/Unlimited-OCR/tree/main) [C]

| File | Bytes | Needed |
|---|---|---|
| model-00001-of-000001.safetensors | 6,672,547,120 (6.67 GB) | yes |
| model.safetensors.index.json | 257,611 | yes |
| config.json | 2,881 | yes |
| modeling_unlimitedocr.py | 53,431 | yes |
| modeling_deepseekv2.py | 90,162 | yes (Apache-2.0 header, see License) |
| deepencoder.py | 38,008 | yes |
| configuration_deepseek_v2.py | 10,720 | yes |
| conversation.py | 9,253 | yes |
| processor_config.json | 466 | yes |
| special_tokens_map.json | 801 | yes |
| tokenizer.json | 9,979,544 | yes |
| tokenizer_config.json | 165,938 | yes |
| LICENSE | 1,061 | keep (MIT notice) |
| README.md | 11,108 | optional |
| .gitattributes | 302 | no |
| Unlimited-OCR.pdf | 460,324 (LFS sha256 d4cc0b2e…) | no |
| assets/long-horizon-ocr.gif | 82,173,303 | no |
| assets/Unlimited-OCR.png | 106,286 | no |
| assets/baidu.png | 11,109 | no |
| wheel/sglang-0.0.0.dev11416+g92e8bb79e-py3-none-any.whl | 12,450,224 | no (Apache-licensed, do not redistribute under the MIT label) |

- Weights LFS sha256 `2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6`; xetHash `56e1945a78f43c9777337ff08075d280552b25791889d4a4ccc85ee82386a517` (Xet-stored).
- usedStorage 6,767,737,257 B (~6.3 GiB; tree page shows 6.78 GB); **20 siblings** [FC, sheet said 19; the table above has 20 rows]. Needed payload (incl. LICENSE + README) = 6,683,168,104 B = 6.68 GB [FC, sheet said ≈6.69]; skippable 95,201,548 B (~95 MB).
- No `generation_config.json`, no GGUF in the official repo.
- API (https://huggingface.co/api/models/baidu/Unlimited-OCR): private=false, gated=false, disabled=false; createdAt 2026-06-19T09:40:33Z; lastModified 2026-07-29T04:34:16Z; downloads 1,826,036; likes 4,304 (4,306 at re-check); library_name transformers; pipeline_tag image-text-to-text; tag custom_code.
- Weights uploaded once (2026-06-22). Every later commit is "Update README.md" (https://huggingface.co/baidu/Unlimited-OCR/commits/main, https://huggingface.co/api/models/baidu/Unlimited-OCR/commits/main, https://github.com/baidu/Unlimited-OCR/commits/main). Pinning the revision is safe.
- [FC] The 6 remote-code/config files at the initial commit `d549bb9d` were byte-compared against main: identical. [C]
- Issue #66 tested revision `84757cb0`, an earlier README-only commit.

**License** [FC, narrowed]
- Repo-level licence MIT (Baidu): "MIT License / Copyright (c) 2026 Baidu" (https://raw.githubusercontent.com/baidu/Unlimited-OCR/main/LICENSE, https://huggingface.co/baidu/Unlimited-OCR/raw/main/LICENSE; 1,061 B; git sha1 890d455ae73d1d930eee703ce1e5478783ec9154, identical on GitHub and HF). GitHub API spdx_id MIT; card metadata `license: mit`, tag `license:mit`. [C]
- The code bundle is mixed MIT + Apache-2.0, not pure MIT [C]:
  - `modeling_deepseekv2.py` lines 2–19: "Copyright 2023 DeepSeek-AI and The HuggingFace Inc. team. All rights reserved. ... Licensed under the Apache License, Version 2.0" (https://huggingface.co/baidu/Unlimited-OCR/raw/main/modeling_deepseekv2.py).
  - `deepencoder.py` is adapted from facebookresearch/detectron2 (ViTDet backbone, batch_norm), facebookresearch/ConvNeXt and facebookresearch/mvit (lines 588, 589, 605, 943), plus a CLIP vision tower; no licence headers. Upstreams are Apache-2.0 (detectron2, mvit) / MIT (https://huggingface.co/baidu/Unlimited-OCR/raw/main/deepencoder.py).
  - `conversation.py` begins "From https://github.com/lm-sys/FastChat/blob/main/fastchat/conversation.py" (FastChat is Apache-2.0) (https://huggingface.co/baidu/Unlimited-OCR/raw/main/conversation.py).
  - The bundled sglang wheel declares "License :: OSI Approved :: Apache Software License" (https://huggingface.co/baidu/Unlimited-OCR/resolve/main/wheel/sglang-0.0.0.dev11416%2Bg92e8bb79e-py3-none-any.whl).
  - The repo ships no Apache licence text, only the MIT LICENSE.
- If the app ships or patches `modeling_deepseekv2.py`, Apache-2.0 section 4 applies: keep the header, include the Apache-2.0 text, mark the file as modified. Add a third-party notices file to the app.
- The MIT grant over the weights rests only on the repo LICENSE file and the card tag. README and paper say nothing explicit about weights, commercial use or redistribution; no GitHub issue or HF discussion addresses licensing (https://huggingface.co/baidu/Unlimited-OCR/discussions). Parent `deepseek-ai/DeepSeek-OCR` is also MIT and ungated (https://api.github.com/repos/deepseek-ai/DeepSeek-OCR, https://huggingface.co/api/models/deepseek-ai/DeepSeek-OCR, https://huggingface.co/deepseek-ai/DeepSeek-OCR/raw/main/LICENSE). [L, normal reading]
- Paper is CC BY 4.0. [C]
- Redistribution or mirroring of weights is permitted if the copyright and permission notice is kept (reading of MIT, not legal advice).

**Official quantized or smaller variants** [C]
- None. Issue #9 (2026-06-23) has no maintainer reply (https://github.com/baidu/Unlimited-OCR/issues/9).
- ~30 community quantized repos (https://huggingface.co/models?other=base_model%3Aquantized%3Abaidu%2FUnlimited-OCR). An HF search for "Unlimited-OCR" returned 100 repos.

**Upstream repo health** (https://api.github.com/repos/baidu/Unlimited-OCR) [C]
- 26,407–26,409 stars, 2,757–2,758 forks (26,427 / 2,760 at re-check), 79 open issues, last push 2026-07-29T04:37:03Z.
- 0 merged PRs. Community CPU/MPS patches #49, #56, #57 never merged. Only contributor: MurphyYin, 13 commits (https://api.github.com/repos/baidu/Unlimited-OCR/contributors, https://api.github.com/users/MurphyYin).
- [FC] Maintainers rarely reply, but the earlier "no reply to any sampled issue" was wrong: **#3 and #25 were answered** by MurphyYin (Youyang Yin, "Research Intern at Baidu Inc.", first author of the paper); see section 5. No maintainer reply was found on the other sampled technical issues (#9, #14, #45, #47, #53, #55, #58, #66, #79, #81, #82, #84, #90). Web-page summaries of GitHub issues reported "Comments: None" while the API shows comments, so the remaining "no reply" entries rest on the same method and are [L]. Still expect no upstream fixes.
- Repo tree (https://api.github.com/repos/baidu/Unlimited-OCR/git/trees/main?recursive=1): .gitignore, CONTRIBUTING.md (https://raw.githubusercontent.com/baidu/Unlimited-OCR/main/CONTRIBUTING.md), LICENSE, README.md (11,585 B), Unlimited-OCR.pdf, infer.py (11,180 B), assets/, wheel/. No requirements.txt (raw URL 404), pyproject or setup.py.
- Timeline: 2026-06-22 release; 06-23 arXiv + ModelScope; 06-24 HF Space; 06-28 vLLM; 07-03 Baidu Cloud; 07-21 ms-swift training. README news ends 2026-07-21.

**Future native port**
- transformers PR #46836 by guarin (`UnlimitedOcrForConditionalGeneration`, `UnlimitedOcrProcessor`, model_type `unlimited_ocr`). Claims CPU, device_map, SDPA, flash-attn, batching, `set_prefill_length()`, `no_repeat_ngram_window_size`. Still OPEN (https://github.com/huggingface/transformers/pull/46836). [C]
- Paired HF discussion #13 (refs/pr/13) adds chat_template.jinja, generation_config.json, preprocessor_config.json (https://huggingface.co/baidu/Unlimited-OCR/discussions/13).

**Name collisions** [C]
- `unlimited-ocr.com` (https://unlimited-ocr.com/) and SourceForge "unlimited-ocr" are unrelated to Baidu's model.
- Baidu "Qianfan-OCR" (192 languages, https://cloud.baidu.com/doc/qianfan-docs/s/Qmispikeo) is a different model.
- github.com/Unlimited-OCR/Unlimited-OCR returns 404.

---

## 2 Python API

**Pinned dependencies** (README, https://raw.githubusercontent.com/baidu/Unlimited-OCR/main/README.md, https://huggingface.co/baidu/Unlimited-OCR/raw/main/README.md, https://github.com/baidu/Unlimited-OCR) [C]

```
torch==2.10.0  torchvision==0.25.0  transformers==4.57.1  Pillow==12.1.1
matplotlib==3.10.8  einops==0.8.2  addict==2.4.0  easydict==1.13
pymupdf==1.27.2.2  psutil==7.2.2
```

- Tested by Baidu on "python 3.12.3 + CUDA12.9", "on NVIDIA GPUs". No pip package; pins must be installed by hand. All 10 pins exist on PyPI with Windows cp311/abi3/any wheels.
- GhostCorp additionally installs `tokenizers>=0.22,<0.23 numpy<3 safetensors>=0.4 accelerate>=1.0 tqdm`.
- The remote code also imports numpy, requests, tqdm.
- [FC] `check_imports()` behaviour depends on the load path (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/dynamic_module_utils.py):
  - Hub loading: raises ImportError ("This modeling file requires the following packages that were not found in your environment: ...") if einops, easydict, addict or matplotlib are missing.
  - Local directory (the app's path): 4.57.1 runs `check_imports` on `modeling_unlimitedocr.py` only, covering addict, matplotlib, torchvision, requests, tqdm, numpy, PIL. einops and easydict live in `deepencoder.py` / `modeling_deepseekv2.py` and fail with a plain `ModuleNotFoundError` at import.

**Python 3.11 on Windows is feasible** [C]
- torch 2.10.0 requires Python >=3.10. `torch-2.10.0+cu128-cp311-cp311-win_amd64.whl` exists (https://download.pytorch.org/whl/cu128/torch/), as do cu126, cu130 and cpu builds (https://download.pytorch.org/whl/cu126/torch/, https://download.pytorch.org/whl/cu130/torch/, https://download.pytorch.org/whl/cpu/torch/). torchvision 0.25.0 cp311 win exists on cu128/cu130/cpu.
- No cu129 Windows wheel exists for 2.10.0 (https://download.pytorch.org/whl/cu129/torch/; the 2.10.0+cu129 URL returns 403). The cu129 index has win_amd64 only for 2.8.0 and 2.9.0. README's "CUDA 12.9" is Linux.
- PyPI `torch-2.10.0-cp311-cp311-win_amd64.whl` is CPU-only, 113,723,116 B (https://pypi.org/pypi/torch/2.10.0/json). One angle left this open; the packaging angle confirmed it by size match with the +cpu wheel.
- Install line: `pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128`.
- transformers 4.57.1 (released 2025-10-14) requires Python >=3.9 (https://pypi.org/project/transformers/4.57.1/, https://pypi.org/pypi/transformers/4.57.1/json).
- PyMuPDF 1.27.2.2 ships `pymupdf-1.27.2.2-cp310-abi3-win_amd64.whl` (https://pypi.org/pypi/PyMuPDF/1.27.2.2/json).
- Pillow 12.1.1 ships `pillow-12.1.1-cp311-cp311-win_amd64.whl` (https://pypi.org/pypi/Pillow/12.1.1/json).

**transformers must stay on 4.x**
- `modeling_deepseekv2.py` line 61 does `from transformers.utils.import_utils import is_torch_fx_available`. It exists in 4.57.1 (import_utils.py line 748) and is absent in 5.17.0 (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/utils/import_utils.py, https://raw.githubusercontent.com/huggingface/transformers/v5.17.0/src/transformers/utils/import_utils.py). [C]
- Restore request closed "not planned" (https://github.com/huggingface/transformers/issues/44561; also #45020 closed, https://github.com/huggingface/transformers/issues/45020). Removed in v5.0.0 via PR #37234, merged 2025-04-10 (https://github.com/huggingface/transformers/pull/37234).
- Other 4.x-era imports: `_prepare_4d_causal_attention_mask`, `LlamaAttention`, `ALL_LAYERNORM_LAYERS`, `is_torch_greater_or_equal_than_1_13`.
- Conflict: two angles rated 5.x breakage "likely" or "unconfirmed". The grep of tagged source is the best evidence, so treat 5.x as broken at import.
- User-confirmed working range: 4.46.3 (saved with), 4.55.0 (issue #90, with torch 2.13), 4.57.1 (pin).
- PyPI latest: transformers 5.17.0 (https://pypi.org/pypi/transformers/json), huggingface_hub 2.0.0, hf_xet 1.6.0, pymupdf 1.28.2.
- Side effect: transformers 4.57.1 requires `huggingface-hub<1.0,>=0.34.0`, `tokenizers<=0.23.0,>=0.22.0`, `safetensors>=0.4.3`. See section 6.
- [FC] tokenizers 0.23.0 final was never released (only 0.23.0rc0, 0.23.1, 0.23.2), so the bound resolves to 0.22.x. Current tokenizers 0.23.2 conflicts with transformers 4.57.1 (https://pypi.org/pypi/tokenizers/json). [C]
- [FC] `torch_dtype` is deprecated in 4.57.1 ("`torch_dtype` is deprecated! Use `dtype` instead!", warns once). It still works; GhostCorp already uses `dtype=`. [C]

**flash-attn is not required** (https://huggingface.co/baidu/Unlimited-OCR/raw/main/modeling_deepseekv2.py) [C]
- Lines 65–67: `if is_flash_attn_2_available(): from flash_attn import ...`.
- `ATTENTION_CLASSES = {'eager': DeepseekV2Attention, 'flash_attention_2': DeepseekV2FlashAttention2, 'mla_eager': DeepseekV2Attention, 'mla_flash_attention_2': DeepseekV2FlashAttention2, 'mha_eager': SlidingWindowLlamaAttention}`; `'mha_flash_attention_2'` is commented out.
- Lines 1398–1403: `attn_implementation = ('mla_' if config.use_mla else 'mha_') + config._attn_implementation`. With use_mla=false only `mha_eager` is valid.
- [FC] Do not pass `attn_implementation`. Failure types in 4.57.1 (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/modeling_utils.py): `'sdpa'` raises **ValueError** from `_sdpa_can_dispatch` before the dict lookup (not KeyError); `'flash_attention_2'` raises ImportError if flash_attn is absent, and KeyError `'mha_flash_attention_2'` only if flash_attn is installed. Unset resolves to eager. [C, source reading]
- Class sets `_supports_flash_attn_2 = True` but not `_supports_sdpa`, so transformers defaults to eager.
- No xformers or triton. MoE routing is plain `torch.topk`.
- `deepencoder.py` uses `F.scaled_dot_product_attention`, has `use_flash_attn=False` (line 522), and zero `.cuda()` calls. `torch.compile` appears only in the unused helper `build_sam_fast_vit_b` (lines 1014–1017).
- R-SWA ring buffer: `W = getattr(self.config, '_ring_window', None)` (line 1282); prefill when W is None.

**Official load + infer** [FC: arguments and values as in README, but NOT verbatim. The README also has `import os`, three pages in `image_files`, different comments and a third PDF example. The quote "Does NOT support crop mode" is from the `infer_multi` docstring in `modeling_unlimitedocr.py`, not the README.] [C]

```python
import torch
from transformers import AutoModel, AutoTokenizer

model_name = 'baidu/Unlimited-OCR'
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, trust_remote_code=True,
                                  use_safetensors=True, torch_dtype=torch.bfloat16)
model = model.eval().cuda()

# single image, "gundam" mode (1024 global view + 640x640 tiles)
model.infer(tokenizer, prompt='<image>document parsing.', image_file='your_image.jpg',
            output_path='your/output/dir', base_size=1024, image_size=640, crop_mode=True,
            max_length=32768, no_repeat_ngram_size=35, ngram_window=128, save_results=True)
# single image, "base" mode: base_size=1024, image_size=1024, crop_mode=False

# multi-page / PDF (base mode only; docstring: "Does NOT support crop mode")
model.infer_multi(tokenizer, prompt='<image>Multi page parsing.',
                  image_files=['page1.png', 'page2.png'], output_path='your/output/dir',
                  image_size=1024, max_length=32768, no_repeat_ngram_size=35,
                  ngram_window=1024, save_results=True)
```

**App-adapted load** (local folder, offline, from the download research; [FC] CPU dtype changed to fp32; untested)

```python
import pathlib, torch
from transformers import AutoModel, AutoTokenizer
def load(model_dir):
    d = str(pathlib.Path(model_dir).resolve())            # absolute path, plain folder name
    tok = AutoTokenizer.from_pretrained(d, trust_remote_code=True, local_files_only=True)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    dt = torch.bfloat16 if dev == 'cuda' else torch.float32   # CPU: fp32 until bf16 is tested (see CPU dtype note)
    model = AutoModel.from_pretrained(d, trust_remote_code=True, use_safetensors=True,
                                      torch_dtype=dt, local_files_only=True)  # `dtype=` is the non-deprecated name
    return tok, model.eval().to(dev)   # infer()/infer_multi() still call .cuda() and force bf16 -> needs patched modeling file

text = model.infer(tok, prompt='<image>document parsing.', image_file=png_path,
                   output_path=tmp_dir, base_size=1024, image_size=640, crop_mode=True,
                   max_length=32768, no_repeat_ngram_size=35, ngram_window=128,
                   eval_mode=True)     # returns str, no stdout streamer, skips save_results
```

**Full signatures** (https://huggingface.co/baidu/Unlimited-OCR/raw/main/modeling_unlimitedocr.py, lines 787 and 1139) [C]

```python
infer(self, tokenizer, prompt='', image_file='', output_path='', base_size=1024, image_size=640,
      crop_mode=True, test_compress=False, save_results=False, eval_mode=False, max_length=32768,
      tps_interval=0, no_repeat_ngram_size=0, ngram_window=0, temperature=0.0)
infer_multi(self, tokenizer, prompt='', image_files=None, output_path='', image_size=640,
      save_results=False, max_length=32768, tps_interval=0, no_repeat_ngram_size=0,
      ngram_window=0, temperature=0.0)
```

**Behaviours the app must handle** [C unless noted]
- n-gram guard defaults are 0. The caller must pass 35/128 (single) or 35/1024 (multi) or loops are unguarded.
- `infer_multi` default `image_size=640`, but README passes 1024.
- `max_length` is passed straight to `generate(max_length=...)` (lines 1011, 1035, 1249). It is the total budget (prompt + image tokens + output). There is no `max_new_tokens`. GhostCorp's patch rewrites it to `max_new_tokens=max_length`.
- `gen_kwargs = dict(input_ids, images, images_seq_mask, images_spatial_crop, do_sample=temperature > 0, temperature=temperature if temperature > 0 else None, eos_token_id=tokenizer.eos_token_id, streamer=streamer, max_length=max_length, use_cache=True)`. Greedy by default. No repetition_penalty or num_beams exposed.
- Batch size 1 only (`unsqueeze(0)` everywhere).
- Return values: `infer()` with eval_mode=False returns None. With eval_mode=True it returns the decoded string (line 1056), EOS `<｜end▁of▁sentence｜>` stripped, `.strip()`, and returns before the save_results block, so the two are mutually exclusive. `infer_multi()` always returns `(outputs, output_tokens)` (line 1299) and has no eval_mode.
- [FC] With eval_mode=True the function returns a string only when the prompt contains `'<image>'`; otherwise None.
- Decoding uses `skip_special_tokens=False`, so returned text most likely still contains `<|ref|>`/`<|det|>` tags. One summary claimed "tags removed". [U, check on first run]
- stdout: with eval_mode=False a `TPSTextStreamer(tokenizer, interval=tps_interval, skip_prompt=True, skip_special_tokens=False)` does `print(text, flush=True, end='')`. `infer_multi` always streams.
- [FC] Windowed pywebview/PyInstaller build (`sys.stdout` is None): the hazard was overstated. Both streamers use builtin `print()`, a silent no-op when `sys.stdout` is None (verified locally on Python 3.11). transformers 4.57.1 logging replaces a None `sys.stderr` with `os.devnull`, which covers tqdm in the save_results path once transformers is imported (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/utils/logging.py, https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/generation/streamers.py). `infer_multi` will not crash for this reason. Redirecting stdout or installing a custom streamer remains harmless and is still useful for progress reporting.
- Other print sites: load_image error, banner `===============save results:===============`, test_compress stats.
- `infer()` unconditionally calls `os.makedirs(output_path, exist_ok=True)` and `os.makedirs(f'{output_path}/images', exist_ok=True)`. `output_path` must always be a writable directory.
- `load_image()` accepts only a file path (`Image.open` + `ImageOps.exif_transpose`). PIL objects or bytes need a temp file.
- Paths are built with `/` f-strings. Cosmetic on Windows. [L]
- [FC] **`eval()` on model output (security).** With save_results=True, `infer()` calls Python `eval()` on the generated text when it contains `line_type`, and `extract_coordinates_and_label` evals box strings in both `infer()` and `infer_multi()`. A crafted document could trigger code execution. Use eval_mode=True for single pages; call `infer_multi` with save_results=False and do own post-processing. [C, source reading]
- `SlidingWindowNoRepeatNgramProcessor` (line 354) is a plain class with `__call__(self, input_ids, scores)`, not a `LogitsProcessor` subclass. It is used when both values > 0, else plain `no_repeat_ngram_size`. Pure Python loop over the window each step.
- PR #57 (https://github.com/baidu/Unlimited-OCR/pull/57) claims transformers 4.57 "silently ignores" such objects. v4.57.1 source contradicts this: `_merge_criteria_processor_list` appends it and `LogitsProcessorList.__call__` calls any callable (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/generation/utils.py lines 1349–1384; https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/generation/logits_process.py lines 67–95). [L, re-read by fact-check, not executed] Wrap it in a `LogitsProcessor` subclass or count invocations in the self-test.

**Prompts**
- Only two are documented: `'<image>document parsing.'` and `'<image>Multi page parsing.'`. The prompt must begin with literal `<image>`. [C]
- Commented-out in code, inherited from DeepSeek-OCR: `'<image>\n<|grounding|>Given the layout of the image. '`, `'<image>\nFree OCR. '`, `'<image>\nParse the figure. '`, `'<image>\nExtract the text in the image. '`. Whether they work is [U]. [FC] One data point: issue #90 used `'<image>\nFree OCR.'` and read Latin text correctly on a crop, but full-page runs returned empty.
- Docling first used `'<image>\n<|grounding|>OCR this image.'` and saw "noticeable degradation in OCR text extraction quality" (issue #4030). Use the official prompt.

**Hard-coded CUDA** [C]
- 17 `.cuda()` occurrences on 14 lines: line 582 inside `forward` (`inputs_embeds[idx].masked_scatter_(images_seq_mask[idx].unsqueeze(-1).cuda(), ...)`); 1003–1005, 1028–1030, 1049, 1059, 1070 in `infer()`; 1241–1243, 1259 in `infer_multi()`.
- 3 `torch.autocast("cuda", dtype=torch.bfloat16)` blocks (lines 1018, 1042, 1238).
- 4 hard-coded `.to(torch.bfloat16)` on image tensors (lines 886, 899, 933, 1205).
- No `device` argument. On CUDA-less torch: `AssertionError: Torch not compiled with CUDA enabled` (https://github.com/baidu/Unlimited-OCR/issues/81).
- HF discussion #19: autocast forces bf16 with no fp16/fp32 option; multi-GPU device_map fails (https://huggingface.co/baidu/Unlimited-OCR/discussions/19).

**CPU patch options** [C that they work on CPU]
1. HF PR/discussion #5 (https://huggingface.co/baidu/Unlimited-OCR/discussions/5, open, "Tested on Apple Silicon (M-series / MPS) and CPU"; a user confirmed on Aug 17). `device = next(self.parameters()).device`; `.cuda()` → `.to(device)`; `torch.autocast('cuda', ...)` → `torch.autocast(device.type, ...)`; fix `masked_scatter_` with `mask.expand_as(inputs_embeds[idx]).to(inputs_embeds.device)`.
2. GhostCorp `device_patch.py` regex patch (section 8).
3. say4n monkeypatch: `torch.Tensor.cuda = tensor_cuda`, `torch.nn.Module.cuda = module_cuda`, load fp32.
4. Fork `sabafallah/Unlimited-OCR-Universal` (https://huggingface.co/sabafallah/Unlimited-OCR-Universal, https://huggingface.co/sabafallah/Unlimited-OCR-Universal/raw/main/README.md): same weights, device-agnostic, fp32 on CPU/MPS "reproduces the CUDA results exactly (~13 GB RAM)", requires `attn_implementation='eager'`, **transformers==4.57.1** [FC, exact pin, not "4.57.1+"].
5. PR #56: `patch_model_for_local.py` + `infer_transformers.py`, replaces masked_scatter_ with positional assignment, autocast `enabled=(self.device.type == 'cuda')`.

- Any approach must cover `forward()` (line 582), not just `infer()`.
- dtype pitfall: mixing fp32 weights with bf16 inputs gives `RuntimeError: Input type (struct c10::BFloat16) and bias type (float) should be the same` (note.com test, Windows, GTX 1060 3GB). Unify all dtypes.
- [FC] **CPU dtype: default to fp32.** The sabafallah card selects float32 on MPS and CPU and says bf16 rounding flips the MoE top-6-of-64 routing so decode "drifts into repeated garbage" (stated for MPS). Issue #81 reports correct CPU output with bf16 autocast. Evidence conflicts. Naive bf16 on non-Sapphire-Rapids x86 is also 9–20x slower (section 3). Use fp32 on CPU until tested, with all dtypes unified. [L]

**Alternative servers, not native Windows** [C]
- vLLM: docker `vllm/vllm-openai:unlimited-ocr` (CUDA 13.0) and `:unlimited-ocr-cu129` (Hopper), vLLM 0.25.0+. "vLLM does not support Windows natively" (https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html). [FC] The vLLM docs also point to a community Windows fork (SystemPanic/vllm-windows); untested here. [U]
- vLLM flags: `--trust-remote-code --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor --no-enable-prefix-caching --mm-processor-cache-gb 0`. Client: `max_tokens=8192`, `temperature=0.0`, `extra_body {'skip_special_tokens': False, 'vllm_xargs': {'ngram_size': 35, 'window_size': 128}}` (1024 for multi-page).
- SGLang: bundled wheel, `uv venv --python 3.12`, `uv pip install kernels==0.11.7`, `python -m sglang.launch_server --model baidu/Unlimited-OCR --attention-backend fa3 --context-length 32768`. [FC] README is inconsistent: the prose says "pin kernels==0.9.0" while the command installs kernels==0.11.7.
- SGLang docs now require CUDA 13 and retired cu129 (https://docs.sglang.io/get_started/install.html). `fa3` is Hopper-only and fails on Ada GPUs. PR #50 adding `--attention_backend` is unmerged (https://api.github.com/repos/baidu/Unlimited-OCR/issues/50). Issues #46 and #12: SGLang could not instantiate `UnlimitedOCRHFProcessor`. SGLang on Windows is [U].
- [FC] `infer.py` (https://raw.githubusercontent.com/baidu/Unlimited-OCR/main/infer.py) is **not client-only**: it imports subprocess and launches `sglang.launch_server` itself via Popen (lines 97, 121), then acts as HTTP client; README says it "starts the SGLang server automatically". `--model_dir` default `baidu/Unlimited-OCR`, POST `http://127.0.0.1:10000/v1/chat/completions`. Constants: PDF_DPI=300, PROMPT='document parsing.', TEMPERATURE=0, CONTEXT_LENGTH=32768, NO_REPEAT_NGRAM_SIZE=35, NGRAM_WINDOW=128, REQUEST_TIMEOUT=1200, MAX_RETRIES=5, `--concurrency` 8, `--image_mode gundam|base`. Output `{pdf_name}_page_XXXX.md`.
- Baidu's own batch script sends each PDF page as a single-image request. It does not use multi-page mode.
- Issue #17 lists infer.py defects: hard-coded NGRAM params, temp-dir leak, empty .md on failure.

---

## 3 Hardware & speed

**Target machine (local probe, 2026-09-27)** [C]
- NVIDIA GeForce RTX 4080 SUPER, driver 617.14, 16376 MiB VRAM, compute_cap 8.9 (sm_89 Ada, native bf16), nvidia-smi "CUDA UMD Version: 13.4".
- [FC] CPU: Intel Core Ultra 7 265K. No AVX-512/AMX, so it is in the slow-bf16 class; CPU mode means fp32 (13.34 GB RAM, fine with 63.7 GB) or fp32 shims.
- [FC] VRAM in use at probe time (2026-09-27 23:38): 10,961 MiB at 99% utilisation (running game plus desktop apps). Usable VRAM is not 16 GB. The app must check **free** VRAM, not total.
- Windows 11 Pro 10.0.26200; 63.7 GB RAM; Python 3.11.9 only (`%USERPROFILE%\AppData\Local\Programs\Python\Python311`); uv not installed; PyInstaller 6.21.0; WebView2 153.0.4234.48; C: 1631 GB free; no `~/.cache/huggingface`; Smart App Control off.
- Driver 617.14 ≥ 580, so cu126, cu128 and cu130 wheels all work.
- Unprivileged symlink creation fails (Developer Mode absent).

**Speed and memory table**

| Config | Hardware | Figure | Source | Status |
|---|---|---|---|---|
| GPU bf16, transformers eager | RTX 4080 SUPER | no measurement anywhere | n/a | [U], must benchmark |
| GPU bf16, framework/mode unknown | RTX 4090 | "about 200 pages in an hour" ≈ 18 s/page (peterderivaz, 2026-06-23) | https://news.ycombinator.com/item?id=48643426, https://hn.algolia.com/api/v1/search?tags=comment,story_48643426&query=4090 | [C] single anecdote |
| GPU bf16, transformers, gundam single page | RTX 5070 Ti 16 GB (WSL2) | ~13.6 s. Same card: SGLang 200–250 tok/s; 16 GB cannot hold the SGLang server and the transformers model at once | https://github.com/GMfatcat/Unlimited-OCR-Local (demo #70), https://raw.githubusercontent.com/GMfatcat/Unlimited-OCR-Local/main/README.md | [FC] [C] as self-reported (repo's own README) |
| GPU bf16, transformers, **native Windows** | RTX 4060 8 GB | ~62 s/page, ~13 tok/s, peak 7.05 GiB VRAM, ~1,400 output tokens per dense page; "The OCR output was good ... did not loop. The speed was the only problem." | https://github.com/overcuriousity/pdf2epub/pull/41, https://raw.githubusercontent.com/rfntnms/pdf2epub/69d967c4a2b652752fcd3a6a784af5d8250bc57c/HANDOVER.md, https://raw.githubusercontent.com/rfntnms/pdf2epub/69d967c4a2b652752fcd3a6a784af5d8250bc57c/README.md | [FC] [C] as self-reported; only native-Windows GPU transformers measurement found |
| GPU bf16, transformers, Fedora 44 | same RTX 4060 8 GB | 61 s for 3 pages, 178 s for 12 pages ≈ 13.9 s/page incl. ~10 s load, ~7.4 GB; "~4x faster here than it was on Windows"; needed `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` or OOM | same | [FC] [C] as self-reported |
| GPU, vLLM FP8 | same RTX 4060 8 GB | 8 workers ~1.3 s/page; 12 workers ~1.05 s/page; scanned book 60 pages in 92 s | same | [FC] [C] as self-reported |
| GPU bf16, transformers | DGX Spark GB10 | gundam 16.4 s / 9.5 s, base 14.8 / 7.7 / 7.3 s per page; ~6.3 GB VRAM steady; one gundam page returned empty in 0.6 s while base succeeded | https://github.com/baidu/Unlimited-OCR/issues/32 | [FC] [C] as reported |
| GPU bf16, DeepSeek-OCR proxy | "RTX 4090" only in the repo description, README names no GPU | 30–60 s/image, 60–120 docs/hour, 5–8 GB VRAM; last pushed 2025-10-26 | https://github.com/LumiVerseHR/deepseek-ocr, https://raw.githubusercontent.com/LumiVerseHR/deepseek-ocr/main/README.md, https://api.github.com/repos/LumiVerseHR/deepseek-ocr | [L] not this model |
| GPU, transformers vs vLLM | per snippet: Windows 11, RTX 4070 Laptop 8 GB, Ryzen 9 8945H, 16 GB RAM | 273 s/page vs 3.6 s/page (0.23 s batched). Snippets inconsistent: one says Unlimited-OCR 10.9 s/page at 7.74 GB peak VRAM, another ties 273 s → 3.6 s to PaddleOCR-VL | [FC] Aditya Mangal, Medium, "The Ultimate OCR Benchmark: 15 OCR Systems Tested on My RTX 4070 Laptop" (Aug 2026), https://adityamangal98.medium.com/the-ultimate-ocr-benchmark-15-ocr-systems-tested-on-my-rtx-4070-laptop-4a9f2c513349 (403, body unread) | [U] |
| GPU, blog | not given | no timings; only "roughly 6 GB just to load", "12 GB card is a sane floor" | https://dev.to/arshtechpro/unlimited-ocr-parsing-a-40-page-pdf-in-one-pass-without-your-gpu-melting-4mc4 | [FC] [C] for the two quotes; previously mis-cited as the 273 s source |
| GPU, blog | not given | "2-5 seconds on GPU"; hardware table: BF16 minimum 12 GB VRAM, recommended 24 GB | https://www.aimadetools.com/blog/how-to-run-baidu-unlimited-ocr-locally/ | [U] no methodology |
| API server | not given | 1.5–3.2 s/page | Docling issue #3679 (comment) | [C] as reported |
| Server aggregate | engine and GPU not named in the paper ("SGLang" is inference) | 5580 TPS at 512 concurrency ("tokens/s/512 concurrency", Base mode) vs 4951 DeepSeek-OCR (12.7%) | paper | [C], not a desktop number |
| MPS fp32 / CPU | M4 Pro 48 GB | 68 s/page MPS, 42 s CPU. [FC] Both include model load (12.6 s and 3.3 s), single 1-page PDF; pure inference ≈ 55 s and 39 s. PR also says "Expect single-page CPU inference to take several minutes on a typical x86 core." | https://github.com/baidu/Unlimited-OCR/pull/49 | [C] as reported |
| MPS bf16 | M4 Pro 48 GB | ~9 s simple image, ~19 s complex page, ~20 s/image batch; autocast variant 42 s | https://github.com/baidu/Unlimited-OCR/pull/57 | [FC] [C] as reported |
| MPS bf16 | M4 Max | ~35 tok/s (645 tokens, base mode) | PR #56 (https://github.com/baidu/Unlimited-OCR/pull/56) | [C] as reported |
| MPS / CPU | MacBook Air M5, 16 GB, torch 2.10.0 | gundam paper page 49 s MPS / 131 s CPU (byte-identical output); base-mode text image 58 s CPU; 2-page PDF multi-page 181 s CPU; model load 10 s; "Budget roughly 20-60 s per page on MPS" | [FC] https://raw.githubusercontent.com/markwgreenlee/unlimited-ocr-macos/main/README.md | [FC] [C] as reported |
| GGUF BF16, Metal | Apple Silicon | ~7.2 s/page (355 pages in 42 min 44 s), cold start ~15 s, llama.cpp b9770, 144 DPI | https://github.com/whit3rabbit/unlocr, https://raw.githubusercontent.com/whit3rabbit/unlocr/main/README.md | [C] |
| GGUF, Metal | M3 Max 36 GB | BF16 172.5 tok/s; Q8_0 243.7; Q6_K 237.3; Q5_K_M 194.3; Q4_K_M 256.9. [FC] These are "isolated generation throughput" (after load and vision encode), not page throughput. R-SWA BF16 168.2 tok/s | https://huggingface.co/vimalnakrani/unlimited-ocr-gguf, https://huggingface.co/vimalnakrani/unlimited-ocr-gguf/raw/main/README.md | [C] |
| GGUF Q5_K_M, Vulkan | Intel Arc A770, **Fedora 44 (Linux)** | 13.843 s wall for one page, up to 5.441 GiB VRAM, 2.18 GiB RSS | https://github.com/baidu/Unlimited-OCR/issues/99, https://github.com/ggml-org/llama.cpp/pull/24975 (comment) | [C] |
| int8 runtime quantisation of the bf16 shard ("no .focrq"), CPU | aarch64 NEON, 8 threads, macOS Apple Silicon | 14,708.377 ms/page vs HF bf16 CPU 41,276.369 ms (2.8x); second page 8,634 vs 28,862 ms (3.3x). HF transformers bf16 CPU reference: 28.9–42.8 s/page | https://raw.githubusercontent.com/Dicklesworthstone/franken_ocr/main/docs/PERF_LEDGER.md | [C], all 41 ledger rows aarch64, no x86 rows |
| int8 (.focrq), CPU | x86 Windows | "minutes-per-page territory"; users: "Speed very slow" (issue #6, https://github.com/Dicklesworthstone/franken_ocr/issues/6) | franken_ocr README | [U] no number |
| int4 WASM | browser | 80–250 s/page + ~95 s cold load, ~3.6 GB peak RAM, 3.00 GB download | franken-ocr.com (https://franken-ocr.com/) | [C] as reported |
| CPU, transformers patched, **dtype not stated** | Apple M1 Pro 16 GB | ~550 s dense page (~2,700 prefix + ~500 output tokens, ~1 tok/s). [FC] 16 GB RAM, so probably memory-pressure bound; compare franken_ocr's bf16 CPU reference of 30.9 ms/token ≈ 32 tok/s | https://github.com/baidu/Unlimited-OCR/issues/81 | [C] |
| CPU, **bf16 weights with fp32 vision encoders and fp32-widened matmuls** | Intel i5-8400 | "55 seconds" first A4 page; two pages 1 min 21 s (infer_multi); README wording "about a minute per page". Naive bf16: vision encoder "114 seconds per page on an i5-8400 instead of 10" | https://github.com/GhostCorpTech/infinite-ai-text-recognizer, https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/README.md | [FC] [C] as reported, only x86 figure; not pure bf16 |
| CPU, blog | not given | "30-60 seconds per page". [FC] Refers to GGUF under llama.cpp, not transformers | aimadetools | [U] |
| CPU, OpenVINO port | Intel | GPU ~4.85 tok/s, CPU ~0.049 tok/s (32-token and 4-token smoke tests only) | sublatesublate-design/unlimited-ocr-openvino (https://raw.githubusercontent.com/sublatesublate-design/unlimited-ocr-openvino/main/README.md) | not usable |

franken_ocr stage breakdown: vision-encode 4,170 vs 23,443 ms (5.6x), prefill 460 vs 2,257 ms, decode 16.141 vs 30.943 ms/token (1.9x).

**Windows vs Linux** [FC]: the 4x Windows penalty in the pdf2epub report was on an 8 GB card at ~7 GiB peak. Whether it is VRAM spill into WDDM shared memory or something else is unknown. It may or may not apply to a 16 GB card. [U]

**Conflict: CPU speed** ranges 39 s to 550 s per page across sources (different hardware, page density, dtype, load time included or not). No controlled x86 measurement exists. [FC] GhostCorp README: "Only Sapphire Rapids and later can compute in bfloat16 on the processor. On everything else PyTorch falls back to a reference implementation roughly 9-20 times slower than fp32". Plan on about a minute to several minutes per page in fp32 and measure.

**Paper Table 4** ("theoretical inference performance ceiling", prefill fixed at 10 tokens, GPU not named) [C]
- Output tokens/s at 256/512/1024/2048/3072/4096/6144 output length: 7229.52 / 7714.78 / 7840.94 / 7881.11 / 7881.93 / 7905.18 / 7847.71.
- DeepSeek-OCR: 7229.32 / 7468.27 / 7422.50 / 7166.85 / 6790.72 / 6430.21 / 5822.87. 35% faster at 6K.
- Figure 3: FA3 kernel latency constant for R-SWA, growing for MHA.

**VRAM and RAM**
- Weights 6,672,547,120 B = 6.67 GB bf16 (6.214 GiB). Reported load "~6.3 GB VRAM" (issue #32, DGX Spark). [C]
- [FC] "Peak RAM: ~12.6 GB at fp32, ~6.3 GB at bf16" is from **PR #49** (M4 Pro / 48 GB) and is peak **system RAM**, not VRAM. The sheet previously attributed it to PR #57, which contains no such figures. [C]
- vLLM recipe: "a single GPU with >=8 GB VRAM is enough for BF16 inference". [C] [FC] Qualification: the pdf2epub author found "The recipe's bf16 settings do not fit 8 GB next to the desktop" (needed `--quantization fp8 --skip-mm-profiling`; "In bf16 the weights take 6.2 GB, and each page needs another ~400 MB for the vision encoder"). This ~400 MB/page is the only rough encoder-activation figure found. [L]
- KV cache computed from config: 12 layers × 10 KV heads × 128 head_dim × 2 × 2 bytes = 61,440 bytes/token. Full 32,768-token prefill ≈ 2.0 GB (1.875 GiB). R-SWA decode ring of 128 tokens ≈ 7.9 MB (7.5 MiB) constant. [L, computed; arithmetic re-verified]
- [FC] **The earlier "largest job should stay under ~10 GB" is wrong for the transformers path.** `SlidingWindowLlamaAttention._attn_forward` (modeling_deepseekv2.py lines 1285–1309, the only registered `mha_eager` class) does `attn_weights = torch.matmul(query_states, k.transpose(2, 3))` then `nn.functional.softmax(attn_weights, dim=-1, dtype=torch.float32)`. During prefill this materialises a full [1, 10 heads, L, L] matrix per layer: 20 × L² bytes (bf16) plus 40 × L² bytes (fp32 softmax), both alive at once ≈ 60 × L² bytes transient. Computed from code, not executed [L]:

| Job | Prefill L | Transient attention peak | Total with 6.2 GiB weights + KV |
|---|---|---|---|
| 1 gundam page | ~1,800–2,700 | 0.2–0.45 GB | ~7 GB |
| 20 base pages | ~5,460 | ~1.8 GB | ~8.5 GB |
| 40 base pages | ~10,920 | ~7.2 GB | ~14 GiB, borderline on a 16 GB card that also drives the desktop |
| full context | 32,768 | ~64 GB | impossible on any consumer GPU |

- So prefill memory in transformers grows **quadratically** with page count. "Under 10 GB" holds only up to roughly 25 base-mode pages. This independently supports a 10–20 page chunk size. vLLM/SGLang (FA3/paged attention) do not have this term. Consistent with PR #86 (OOM on long PDFs) and the pdf2epub 8 GB OOM.
- aireiter.com matches the KV numbers only: "Model weights: 6.673 GB; 32K prefill cache: 1.875 GiB; R-SWA decode cache: 7.5 MiB" (https://aireiter.com/blog/unlimited-ocr-baidu-api-review). It also models ≈ $1.70 per 1,000 pages single-stream on a 4090 (derived from the single HN anecdote) vs Google Enterprise Document OCR $1.50/1K, saturated batch ~$0.07/1K. [U]
- Spheron formula-based ("within about 15%", batch 1, 4K ctx): FP16 7.3 GB / INT8 3.6 GB / INT4 1.8 GB; bf16 weights ~6.7–7.3 GB (https://www.spheron.network/tools/gpu-recommender/baidu/Unlimited-OCR/). [L]
- Encoder activations at 1024 px and the 32-crop gundam grid: only the ~400 MB/page figure above. Peak VRAM for a 40-page `infer_multi` on 16 GB is [U], estimated ~14 GiB.
- "Prefill still grows with page count, R-SWA solves the decode memory problem but not the prefill memory problem" (secondary).
- GhostCorp tiers (code, https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/probe.rs): Full = sm_80+ and ≥11.5 GiB VRAM; Reduced = sm_80+ below 11.5 GiB; Economy = sm_75 or VRAM-starved (fp16 + NF4); CPU = RAM ≥15 GiB; plus a weights+1 GB fit check. README states ≥12 GB, 8–12 GB, <8 GB, ≥16 GB RAM. Code values are more precise.
- CPU RAM: bf16 weights 6.7 GB; fp32 13.34 GB (~13.3–13.4). [L, derived] [FC] GhostCorp's working CPU configuration (fp32 vision encoders) adds +0.8 GB over pure bf16.
- Reported working GPUs, by runtime [FC]:
  - transformers: RTX 3080 Ti on Windows 11 (issue #58), Tesla T4 (issue #79, Kaggle, torch 2.10.0+cu128, transformers 4.57.1; sm_75, so the path runs on Turing, dtype not stated), RTX 4060 8 GB native Windows (pdf2epub), RTX 5070 Ti (WSL2), L4 (issue #90). "12 GB"/"16 GB" for #58/#79 are hardware-spec inferences, not stated in the issues.
  - vLLM 0.25.1: RTX PRO 5000 (issue #84).
  - SGLang in Docker on Linux: RTX 3060 (say4n PR #1, https://github.com/say4n/unlimited-ocr-container/pull/1).
  - Framework unknown: RTX 4090 (HN).

**Quantized options (no official int8)**

| Variant | Size | Quality evidence | Runtime | Status |
|---|---|---|---|---|
| GGUF BF16 | 5,876,578,080 B = 5.88 GB = 5.47 GiB | 172.5 tok/s M3 Max; [FC] overall CER MHA 0.7792% vs R-SWA 0.3344% (vimalnakrani) | llama.cpp | [C] |
| GGUF Q8_0 | 3,126,139,904 B = 3.13 GB = 2.91 GiB | "identical to BF16 output"; 243.7 tok/s | llama.cpp | [C] |
| GGUF Q6_K | 2.61 GB = 2.43 GiB | "identical to BF16 output"; 237.3 tok/s | llama.cpp | [C] |
| GGUF Q5_K_M | 2.22 GB = 2.07 GiB | CER 0.74%, recommended by vimalnakrani; 194.3 tok/s | llama.cpp | [C] |
| GGUF Q4_K_M | 1,950,326,784 B = 1.95 GB = 1.82 GiB | CER 15.64% "quality cliff" | llama.cpp | [C] |
| GGUF Q4_0 | 1.7 GB | CER 44.02% | llama.cpp | [C] |
| GGUF Q4_K_S / Q3_K_M / IQ3_M / IQ3_XXS / IQ2_M | 1.81 / 1.55 / 1.45 / 1.34 / 1.23 GB | none | llama.cpp | [C] sizes |
| GGUF IQ4_XS / IQ2_M (GiB column) | 1.53 / 1.15 | none | llama.cpp | [L] |
| mmproj F16 (mandatory) | [FC] two different files: sahilchachra 811,876,448 B = 774.27 MiB = 0.756 GiB = 0.81 GB; vimalnakrani/DevQuasar 825,245,568 B = 787 MiB = 0.769 GiB = 0.83 GB | kept F16: "quantizing it hurts OCR accuracy" | llama.cpp | [C] |
| franken_ocr int8 `.focrq` | 4,157,448,783 B | 20-page corpus CER 0.19307925, hard page 0.6164886 | focr.exe, CPU only | [C] |
| AWQ W4A16 (sahilchachra/Unlimited-OCR-AWQ, 1,284,913 downloads; AutomatosX AWQ-W4A16) | 2.82 GB [FC, was "≈2–3 GB"] | card: "OCR output matches BF16" | torch + CUDA + compressed-tensors | [L] |
| NVFP4 (https://huggingface.co/sahilchachra/Unlimited-OCR-NVFP4, https://huggingface.co/sahilchachra/Unlimited-OCR-NVFP4/raw/main/README.md) | ~2.93 GB | "identical to BF16 on tested documents"; 2196 decoder modules | compressed-tensors; dequantized on non-Blackwell (incl. Ada), no speedup | [C] |
| FP8-Dynamic (shadowrock-io) | n/a | n/a | n/a | [L] |
| bitsandbytes NF4 | n/a | GhostCorp: "NOT reference quality", never verified | torch + bitsandbytes | [U] |
| bitsandbytes LLM.int8 | n/a | no report | n/a | [U] |
| MLX variants | n/a | n/a | macOS only | n/a |

- Size conflict resolved: 5.88 vs 5.47, 3.13 vs 2.91, 1.95 vs 1.82 are the same files in decimal GB vs GiB. Exact bytes are pinned by unlocr.
- DevQuasar/baidu.Unlimited-OCR-GGUF: Q3_K_M 1.55 GB … Q8_0 3.13 GB. Other GGUF repos: sabafallah, vimalnakrani, 42ailab, forkjoin-ai, cstr. File listings: https://huggingface.co/api/models/vimalnakrani/unlimited-ocr-gguf/tree/main, https://huggingface.co/api/models/sahilchachra/Unlimited-OCR-GGUF/tree/main, https://huggingface.co/api/models/DevQuasar/baidu.Unlimited-OCR-GGUF/tree/main.
- Download counts: baidu 1.83M, AWQ 1.28M (https://huggingface.co/api/models/sahilchachra/Unlimited-OCR-AWQ), sahilchachra GGUF 10.2k (~10k/month), vimalnakrani 4.5k, DevQuasar 1.4k.
- Conflict on Q4_K_M: sahilchachra's card recommends it; another summary says 8/6/5-bit "carry no measured recognition cost" and 4-bit degrades on dense small fonts; vimalnakrani measured 15.64% CER. The measurement is better sourced. Do not default to Q4.
- Conflict on AWQ: one angle found no AWQ reports; two others list AWQ repos on HF. The repos exist.
- bitsandbytes ships native Windows x86-64 wheels (CUDA 11.8–12.6, 12.8, 13.0–13.2; sm_89 included; NF4/FP4 needs CC 6.0+, LLM.int8 CC 7.5+; Python ≥3.10, PyTorch ≥2.4; CPU build needs AVX2) (https://huggingface.co/docs/bitsandbytes/main/en/installation). [C]
- Not needed on the 16 GB target when VRAM is free. Relevant for a fallback ladder on other machines, and on this one when a game holds ~11 GB.

---

## 4 Inputs & outputs

**Inputs** [C]
- Image files opened by PIL from a path (README examples .jpg/.png). EXIF transpose only. No deskew or rotation detection.
- PDFs: the model never reads PDFs. README helper: `fitz.Matrix(dpi/72, dpi/72)`, `page.get_pixmap(matrix=mat).save('page_0001.png')`, dpi=300. PyMuPDF `get_pixmap` honours `/Rotate`.
- DPI in the wild: 300 (README, infer.py, say4n), 200 (official HF Space, https://huggingface.co/spaces/baidu/Unlimited-OCR/raw/main/app.py), 144 (GhostCorp `PDF_RENDER_DPI`, unlocr via pdftoppm, issue #79's 2x render), 150 (globalaiforce.com).
- The model pads or resizes to 1024x1024 (base) or 640 px crops (gundam). A 300-DPI A4 (~2480x3508) is downscaled to 1024 in base mode; >300 DPI adds nothing. Issue #82 comments recommend 300 DPI to reduce looping. No official DPI range.

**Resolution modes** [C]
- gundam: `base_size=1024, image_size=640, crop_mode=True`. Global view = `ImageOps.pad(image, (1024,1024))` with mean-colour padding, plus `dynamic_preprocess(image, min_num=2, max_num=32, image_size=640, use_thumbnail=False)` tiles.
- [FC] `infer()` calls `dynamic_preprocess(image)` with defaults, so tiles are always 640 px regardless of the `image_size` argument. `crop_mode=True` must be paired with `image_size=640`. Images with both sides ≤640 px get no tiles at all.
- base: `image_size=1024, crop_mode=False`, single padded view.
- Multi-page must use base. vLLM: "Single-image requests use gundam (crop) mode; multi-image requests automatically switch to base mode". The HF Space likely runs base, which loses small text on tall pages.

**Vision token budget**
- num_queries = ceil((size // 16) / 4): 16 for 1024, 10 for 640.
- Base page = (16+1)×16+1 = **273** tokens.
- Gundam adds (10·w+1)·(10·h) for a w×h crop grid. A 3×5 grid = 1550, total 1823.
- Conflict 256 vs 273: the paper's 256 counts visual tokens before separators. 273 is derived from code and corroborated by vLLM issue #63's error "Attempted to assign 273 = 273 multimodal tokens to 1823 placeholders" for a 1700x2800 image (https://github.com/baidu/Unlimited-OCR/issues/63). 273 is better sourced.
- Issue #81 saw ~2,700 prefix tokens for a dense gundam page (~24 crops). Exact separator counts in gundam are [U]; measure with the tokenizer.

**Page budget** [C, derived]
- 32,768 total. 200 pages × 273 = 54,600 exceeds it, so a long PDF must be chunked.
- 40 pages = 10,920 prefill tokens, leaving ~21,800 output tokens (~545 per page). Dense pages (1,000–2,000 tokens; pdf2epub measured ~1,400) would hit the cap; `generate` just stops, silently.
- [FC] The binding limit on the transformers path is VRAM, not the token budget: ~25 base pages keeps the job under ~10 GB, 40 pages needs ~14 GiB (section 3).

**Multi-page accuracy** (paper Table 3, in-house benchmark, base mode) [C]

| Pages | 2 | 5 | 10 | 15 | 20 | 40+ |
|---|---|---|---|---|---|---|
| Edit distance | 0.0362 | 0.0452 | 0.0526 | 0.0787 | 0.0572 | 0.1069 |
| Distinct-35 | 99.87% | 99.98% | 99.83% | 99.99% | 99.89% | 96.90% |

- Distinct-20 at 40+ pages: 96.08%.
- Errors occur "where small text in the PDF is difficult to discern, primarily due to the use of DeepEncoder's Base mode".
- Implied chunk size: 10–20 pages.

**Output format** [C unless noted]
- Text interleaved with grounding tags: `<|ref|>{label}<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>` and the variant `<|det|>label [x1,y1,x2,y2]<|/det|>`.
- Source regexes: `ref_pattern = r'(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)'` and `det_pattern = r'(<\|det\|>\s*([A-Za-z_][\w-]*)\s*(\[[^\]]+\])\s*<\|/det\|>)'`.
- README cleaner: `DET_RE = re.compile(r'<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)', re.DOTALL)` + `remove_det()` (drops `image` blocks, joins lines of a block with `\n`, blocks with `\n\n`).
- Coordinates normalized 0–999, rescaled `int(x/999*width)`. The paper says "0–1000" and separator `<page>`; code says 0–999 and `<PAGE>`. Code is authoritative.
- Multi-page output delimited by literal `<PAGE>`. `infer_multi` maps pages by index; pages beyond `len(images)` are appended raw.
- Stop string `<｜end▁of▁sentence｜>`.
- `skip_special_tokens=True` anywhere strips the layout markers and returns flat text.
- Docling: the model "emits grounding annotations, not markdown — with both prompts".
- Tables and formulas: the official-docs angle found no primary statement. Two other angles report HTML tables + LaTeX formulas, supported by the sabafallah card ("aggressive DRY settings garble the model's HTML table output") and issue #84 ("huge HTML tables"). [FC] Additional support: the tokenizer has dedicated added tokens `<td>`, `</td>`, `<tr>`, `</tr>` (ids in 128800–128826, https://huggingface.co/baidu/Unlimited-OCR/raw/main/tokenizer_config.json). Upstream post-processing rewrites `\coloneqq`/`\eqqcolon` to `:=`/`=:`. HTML tables [L, strong]; LaTeX [L]; verify locally.
- Element labels, no official list (issue #51 closed without reply, https://github.com/baidu/Unlimited-OCR/issues/51): title, header, text, image, figure, image_caption, table, table_caption, list, formula, page_number, footer (from GMfatcat's `LABEL_COLORS`). [L]
- `save_results=True`, single: `result.md`, `result_with_boxes.jpg`, `images/{idx}.jpg`; `geo.jpg` only if output contains `line_type` (this branch runs `eval()` on model output, see section 2).
- `save_results=True`, multi: `result.md` with `<PAGE>` separators, `result_with_boxes_{page}.jpg`, `images/page_{page}_{idx}.jpg` (lines 1267–1299).
- Image regions `<|ref|>image<|/ref|>...` are cropped and replaced by `![](images/{prefix}{idx}.jpg)\n`; other `<|det|>` tags are dropped.
- Quirks: headings sometimes emitted without `#` (issue #68, open, PR #72 referenced); issue #18 requests an option to keep detection tags; no cross-page paragraph merging or header/footer removal (issue #47).
- HF Space demo source (issue #94) and a visualization module (issues #5/#6) are apparently not published. [U]

**Benchmarks**
- OmniDocBench v1.5 (paper Table 1), columns Overall / Text Edit / Formula CDM / Table TEDS / TEDS-S / Read-order Edit [C]:
  - Unlimited-OCR 93.23 / 0.038 / 92.61 / 90.93 / 94.07 / 0.045
  - DeepSeek-OCR 87.01 / 0.073 / 83.37 / 84.97 / 88.80 / 0.086
  - DeepSeek-OCR 2 89.17 / 0.049 / 86.85 / 85.60 / 90.06 / 0.060
  - dots.ocr 88.41 / 0.048 / 83.22 / 86.78 / 90.62 / 0.053
  - olmOCR 7B 81.79 / 0.096 / 86.04 / 68.92 / 74.77 / 0.121
  - MinerU2-VLM 85.56 / 0.078 / 80.95 / 83.54 / 87.66 / 0.086
  - Overall only: Qwen2.5-VL-72B 87.02, Gemini-2.5 Pro 88.03, GPT-4o 75.02
- v1.6 (paper): Unlimited-OCR 93.92 / 0.042 / 95.79 / 90.16 / 93.32 / 0.129. Others overall: DeepSeek-OCR 2 90.25, dots.ocr 90.77, FireRed-OCR 93.26, Logics-Parsing-v2 93.33, Qianfan-OCR 93.90, HunyuanOCR 89.95.
- OmniDocBench repo leaderboard v1.6 (https://github.com/opendatalab/OmniDocBench, https://raw.githubusercontent.com/opendatalab/OmniDocBench/main/README.md): Unlimited-OCR 94.00 (text 0.0394, formula 95.72, TEDS 90.21, order 0.1281). Behind PaddleOCR-VL-1.6 96.34 (0.0326 / 97.53 / 94.76 / 0.1278), MinerU2.5-Pro 95.75, GLM-OCR 95.22, PaddleOCR-VL-1.5 94.93. Ahead of Gemini 3 Pro 92.91, dots.ocr 90.77, DeepSeek-OCR-2 90.25, GPT-4o 86.59, Mistral OCR (3) 85.66 (TEDS 76.78), Marker 78.44.
- Minor conflicts: paper 93.92 vs leaderboard 94.00; PaddleOCR-VL-1.6 96.33 (HF card) vs 96.34 (leaderboard).
- Disputed (issue #66, https://github.com/baidu/Unlimited-OCR/issues/66): independent run got text EditDist 0.087 vs ~0.042 (gundam, greedy, 35/128, bf16, 1,651 pages) while matching Formula CDM 0.9583 and TEDS 0.9022. No maintainer reply. Real text accuracy may be ~2x worse than the headline.
- Issue #14 (open, https://github.com/baidu/Unlimited-OCR/issues/14): users report SGLang output "much better" than transformers on multi-page PDFs. Unexplained.
- olmOCR-bench: no Unlimited-OCR score [U]. Mistral OCR 4 (2026-06-23) claims 85.20 and a 72% human-preference win rate over 600+ documents; olmOCR 2 82.4; Marker 76.1; MinerU 75.8 (https://allenai.org/blog/olmocr-2, https://www.computeleap.com/blog/baidu-unlimited-ocr-vs-mistral-ocr-4-document-parsing-2026/, https://www.aimadetools.com/blog/baidu-unlimited-ocr-complete-guide/). Mistral is cloud, $4 per 1K pages. [L]
- No Tesseract comparison exists. [U]

---

## 5 Language support incl. Czech

**Bottom line: Czech is untested by anyone. Baidu's maintainer states in writing that this version mainly supports English and Chinese. Do not commit without a local acceptance test.** [FC: survives, better supported than before]

**What Baidu says**
- HF card YAML: `language: - multilingual` only. README, paper and card list no languages and never mention handwriting. [C]
- [FC] **Primary statements by MurphyYin** (author_association CONTRIBUTOR; Youyang Yin, Research Intern at Baidu; first author of arXiv 2606.23050) [C]:
  - Issue #3, 2026-06-23: "In this version, we mainly support English and Chinese." (https://github.com/baidu/Unlimited-OCR/issues/3#issuecomment-4775541489)
  - Issue #3, 2026-06-25: "We are currently collecting more multilingual training data and plan to release a future version of the model with language coverage aligned as closely as possible with the Deepseek-OCR supported language list." (https://github.com/baidu/Unlimited-OCR/issues/3#issuecomment-4802136769)
  - Issue #25, 2026-06-25: "We currently mainly support Chinese and English. We are collecting more multilingual datasets for training, and plan to release a future version of the model with broader language support." (https://github.com/baidu/Unlimited-OCR/issues/25#issuecomment-4802120913)
  - Issue #25, 2026-06-25: team is "discussing fine-tuning support" (https://github.com/baidu/Unlimited-OCR/issues/25#issuecomment-4801431107).
  - Issue #3 has 7 comments, #25 has 6 (https://api.github.com/repos/baidu/Unlimited-OCR/issues/3/comments, https://api.github.com/repos/baidu/Unlimited-OCR/issues/25/comments; issue pages https://github.com/baidu/Unlimited-OCR/issues/3, https://github.com/baidu/Unlimited-OCR/issues/25).
- Baidu staff ChengCui (BAIDU org), HF discussion #8, 2026-07-09: "Multi-language support will be available in the next release. Alternatively, you can consider using PaddleOCR-VL-1.6, which already provides a certain level of Arabic recognition capability." (https://huggingface.co/baidu/Unlimited-OCR/discussions/8) [C]. This contradicts the "multilingual" tag.
- No next release has shipped as of 2026-09-27. baidu HF org has only Unlimited-OCR (last modified 2026-07-29) and Qianfan-OCR (https://huggingface.co/api/models?author=baidu&sort=lastModified&direction=-1&limit=30); PaddlePaddle/Unlimited-OCR on HF returns 401 (https://huggingface.co/api/models/PaddlePaddle/Unlimited-OCR). [C]
- INSIDE (Taiwan, 2026-06-25), attributed to an official explanation: supports Chinese and English bilingual and mixed documents (https://www.inside.com.tw/article/41650-baidu-unlimited-ocr). [FC] Upgraded to [C]: the primary Baidu text is the #3 comment, dated two days earlier.
- Baidu Cloud API doc (https://cloud.baidu.com/doc/OCR/s/fmr1p39gb) and launch notice 2026-07-06 (https://ai.baidu.com/support/news?action=detail&id=3274) list parameters (file_data / file_url / file_name / angle_adjust / angle_mode [FC, added] / erase_seal / erase_watermark / unwarp) and QPS (submit 2, poll 5) but no language list. [C]
- [FC] Unanswered language question: only HF discussion #22 (created 2026-09-13, https://huggingface.co/baidu/Unlimited-OCR/discussions/22). A user in #3 asked for Italian support (2026-07-29). [C]

**Benchmarks cover only EN/ZH**
- OmniDocBench README: "1651 PDF pages, covering 10 document types, 5 layout types, and 5 language types". [FC] Its attribute definitions list only three language values (english, simplified_chinese, en_ch_mixed); the other two are not named. The Unlimited-OCR paper does not describe the benchmark's language composition. No European language appears in any number Baidu publishes. [C]
- The only handwriting-related number: "Note" row (zh/en handwritten notes) text-edit 0.066 vs DeepSeek-OCR 0.145.

**Inherited ability**
- DeepSeek-OCR training: "30M pages of diverse PDF data covering about 100 languages", Chinese and English ≈ 25M, other languages 5M; 600K minority-language samples via GOT-OCR2.0 flywheel; scene OCR "mainly supports Chinese and English" (https://arxiv.org/html/2510.18234v1). [C]
- The 4,000-step continue-train used PaddleOCR-labelled data of unknown language mix. Minority-language ability may have been partly forgotten. [U]
- [FC] The Vietnamese report is weak evidence for forgetting: the parent was already weak on Vietnamese in MORE (DeepSeekOCR vi overall 62.86, text 91.44 vs HunyuanOCR 96.74; against cs text 96.67). The failure may be inherited, and Vietnamese is an imperfect analogue for Czech.

**Tokenizer** [FC, upgraded from [L] to [C] by reading tokenizer.json]
- `tokenizer.json` (https://huggingface.co/baidu/Unlimited-OCR/resolve/main/tokenizer.json): model type BPE, ByteLevel pre-tokenizer and decoder, unk_token None, 128,000 BPE vocab entries + 830 added tokens = vocab 129280. tokenizer_class `LlamaTokenizerFast`.
- Matches the DeepSeek-V3 tokenizer description ("Byte-level BPE with an extended vocabulary of 128K tokens", https://arxiv.org/html/2412.19437v2).
- All 15 lowercase Czech diacritic letters (ř ů ě č š ž ď ť ň á é í ó ú ý) have a dedicated single token (e.g. ř 3993, ů 6474, ě 3145, č 3526, ž 3634). Czech word tokens exist ("Ġpří", "Ġkterý", "Ġže", "Ġjsou", "Ġnebo"). Uppercase Ř, Ů, Ď, Ť, Ň have no merged token and encode as two byte tokens, still lossless.
- [FC] Added tokens (https://huggingface.co/baidu/Unlimited-OCR/raw/main/tokenizer_config.json): **800 placeholders at ids 128000–128799** (sheet said 512), then 128800–128826 specials including `<image>`, `<|ref|>`, `<|/ref|>`, `<|det|>`, `<|/det|>`, `<|grounding|>`, `<td>`, `</td>`, `<tr>`, `</tr>`.
- Encodability says nothing about recognition accuracy.

**Best proxy for Czech: parent model on MORE** (Tencent, ICML 2026, 149 languages, arXiv 2607.02956, 2026-07-03, https://arxiv.org/html/2607.02956, https://arxiv.org/abs/2607.02956, https://github.com/zimoqingfeng/MORE) [C; values re-parsed from Tables 15/16 and match, so the earlier "not cross-checked" caveat is dropped]

Per-language "Overall" (mean of only the tasks present):

| Model | cs | pl | de | hu | sk | Overall (149 langs) |
|---|---|---|---|---|---|---|
| DeepSeekOCR (parent) | 98.34 | 96.84 | 90.74 | 99.26 | 96.57 | 82.91 |
| HunyuanOCR | 98.98 | 99.10 | 98.10 | 99.73 | 99.06 | 92.42 |
| dots.ocr | 99.58 | 98.75 | 94.20 | 99.19 | 99.66 | 84.31 |
| PaddleOCR-VL | 97.37 | 98.38 | 97.24 | 99.37 | 98.33 | 87.96 |
| Qwen3-VL | 94.78 | 96.41 | 97.80 | 98.80 | 88.68 | 83.56 |

[FC] Text-only scores (MORE Table 17), the relevant number for diacritics:

| Lang | HunyuanOCR | Qwen3-VL | Qwen2.5-VL | dots.ocr | PaddleOCR-VL | DeepSeekOCR | MinerU2.5 |
|---|---|---|---|---|---|---|---|
| cs | 97.96 | 94.49 | 96.01 | 99.16 | 94.73 | 96.67 | 60.51 |
| de | 99.84 | 99.38 | 99.67 | 99.90 | 99.93 | 91.54 | 72.68 |
| pl | 98.90 | 97.68 | 97.99 | 98.92 | 98.30 | 94.23 | 60.41 |
| sk | 98.13 | 97.36 | 96.13 | 99.33 | 96.66 | 93.14 | 35.09 |
| hu | 99.46 | 99.03 | 98.08 | 99.82 | 98.74 | 98.52 | 36.70 |
| fr | 99.90 | 99.80 | 99.28 | 99.96 | 99.97 | 92.73 | 53.40 |

- [FC] Caveats that make the overall table overstate the parent's Czech ability:
  - Czech sample is 9 pages, 96 paragraphs, 0 formulas, 0 tables, 0 code, 0 catalogs (Table 13). Sampling: "up to 10 PDFs per language and extracting a single random page from each file". Statistically very thin.
  - DeepSeekOCR cs 98.34 = (96.67 text + 100.00 reading order) / 2. Text alone ≈ 3.3% normalised edit distance on 9 pages.
  - On text, DeepSeekOCR is the weakest non-MinerU model for German, Polish, Slovak and French (5–8 points behind the leaders) and mid-pack for Czech.
- Other overalls: Gemini 3 91.61 (no per-language scores), Qwen2.5-VL 83.93, MinerU2.5 48.85.
- Unlimited-OCR itself is not in MORE. "Latin group predominates (53.69%)". Nothing specific on diacritics (the word does not occur in the HTML).
- [FC] "Printed documents only" is **not** a statement in the MORE paper. The words printed, scanned, handwritten, photograph and born-digital do not occur. It says samples are web-crawled real-world PDFs, "devoid of any synthesis or artificial processing". MORE therefore says nothing about scanned or photographed Czech pages, the app's actual use case. Page count is 1,288 in Tables 1/3 and 1,237 in the text. The PaddleOCR-VL tested is the original 0.9B / 109-language model, not 1.6.

**Community evidence on Unlimited-OCR itself**
- Vietnamese (Latin script, heavy diacritics): negative. HF discussion #14 (2026-07-22): "repetitive words, wrong characters"; follow-up 2026-08-18: "results aren't good enough". No Baidu reply. (https://huggingface.co/baidu/Unlimited-OCR/discussions/14) [C] See the parent-weakness caveat above.
- Hebrew/Latin invoice (issue #90, 2026-08-04): Latin "Master-Coach" and "10707" read correctly; all Hebrew hallucinated as a fixed nonsense (niqqud) token. [FC] Test conditions: non-official prompt `'<image>\nFree OCR.'` (an earlier run used `<|grounding|>`), transformers 4.55.0, "CUDA build of torch 2.13", L4 GPU; full-page runs returned empty in all three modes. (https://github.com/baidu/Unlimited-OCR/issues/90, https://api.github.com/repos/baidu/Unlimited-OCR/issues/90) [C]
- Bengali "detects as Hindi" (https://huggingface.co/spaces/baidu/Unlimited-OCR/discussions/6, 2026-08-02). Arabic unsupported (https://github.com/baidu/Unlimited-OCR/issues/89 2026-08-03, https://github.com/baidu/Unlimited-OCR/issues/95 2026-08-12, 0 comments each; HF #8). [C]
- Japanese + English: positive (HN, RTX 4090, no unwanted translation). General risk remarks in the same thread: LLM-OCR may translate foreign words; "Vietnamese have easily confused diacritics". [C]
- Devanagari stress test (arXiv 2606.29213, https://arxiv.org/html/2606.29213): CER clean synthetic 3.20%, blur (Gaussian σ 1.0–1.8) 6.14%, noise (6% pixels) 4.17%, low-DPI (0.45x) 4.49%. On 300 real printed scans: mean CER 359.8% (median 50%, 46.7% catastrophic, 4.0x output-length ratio, chrF++ 24.7), 9th of ten systems, ahead only of DeepSeek-OCR (chrF++ 10.4). Clean chrF++ 91.0 vs DeepSeek-OCR 93.8. Rotation, JPEG and skew not tested. [C]
- Czech, Polish, German, Hungarian: no data either way. [FC] One unsupported claim on record: in issue #25 a non-maintainer (kushdab, association NONE) asserts the model "can often extract Latin-script languages (French, German, Spanish, etc.) with reasonable quality — just without any guarantees or benchmarks"; no samples. [U]
- Searched GitHub issues, all 20 HF model discussions (numbers run to 22; https://huggingface.co/api/models/baidu/Unlimited-OCR/discussions?p=0&status=all), Space discussions, HN, Reddit, Chinese web, blogs (https://github.com/baidu/Unlimited-OCR/issues?q=is%3Aissue+language+OR+multilingual+OR+german+OR+polish+OR+czech+OR+french+OR+spanish+OR+cyrillic+OR+arabic+OR+handwriting+OR+handwritten). GitHub search API returns 0 hits for czech, diacritics, turkish, european, umlaut, accent, russian, cyrillic in baidu/Unlimited-OCR (https://api.github.com/search/issues?q=repo:baidu/Unlimited-OCR+czech) and 0 for czech/polish/german/slovak/hungarian/diacritics/umlaut in deepseek-ai/DeepSeek-OCR (249 issues; https://api.github.com/search/issues?q=repo:deepseek-ai/DeepSeek-OCR+czech). [C]
- Blog claim of "solid Cyrillic support" and handwritten math (https://codersera.com/blog/run-baidu-unlimited-ocr-locally-2026/): no source. [U]

**Why diacritics are at risk**
- "Visual Merit or Linguistic Crutch? A Close Look at DeepSeek-OCR" (Liang et al., 2026-01-07, https://arxiv.org/abs/2601.03714): "without linguistic support, DeepSeek-OCR's performance plummets from approximately 90% to 20%". Fewer visual tokens means more reliance on language priors. [C]
- Implication: unfamiliar Czech names and terms tend to be "autocorrected". Prefer gundam mode for Czech (tiles are fixed at 640 px, so a higher `image_size` does not help in gundam).

**Handwriting**
- No official claim. Only user report is negative (issue #45, Chinese handwritten notes, 6 comments, no maintainer; a second user, jason-ni, agreed and reported dots.ocr as more accurate on the same sample; https://github.com/baidu/Unlimited-OCR/issues/45). HF #14 question on handwritten Vietnamese unanswered. Handwritten Czech: no evidence. [C]

**Fallback engine**
- PaddleOCR-VL (generic 0.9B doc) explicitly lists Czech, Slovak, Polish, Hungarian and German among 109 languages and claims handwriting and historical documents (https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/docs/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.en.md). [C] The doc does not mention version 1.6.
- PaddleOCR-VL-1.6: 1.0B params (0.9B per another source), Apache-2.0, 96.33 on OmniDocBench v1.6 (https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6, https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6/raw/main/README.md). [FC] Its card lists only "en, zh, multilingual" and no per-language list, so Czech support in 1.6 is inherited/assumed. [L]
- [FC] In MORE overall scores PaddleOCR-VL beats DeepSeekOCR on Polish, German, Slovak **and Hungarian** (99.37 vs 99.26), but not Czech (97.37 vs 98.34). On Czech text-only it is also behind (94.73 vs 96.67). Best Czech text score: dots.ocr 99.16, then HunyuanOCR 97.96.

---

## 6 Weight download & one-time caching

**Hosting facts** [C]
- HF repo public, not gated, no token. Official docs use plain `from_pretrained('baidu/Unlimited-OCR')`; no custom downloader.
- REST: `GET https://huggingface.co/api/models/baidu/Unlimited-OCR` (sha, gated, siblings); `GET .../tree/main[/<subdir>]` (path, size, oid, lfs.oid = sha256, lfs.size, xetHash; https://huggingface.co/api/models/baidu/Unlimited-OCR/tree/main?recursive=true); files from `https://huggingface.co/baidu/Unlimited-OCR/resolve/<revision>/<filename>` (https://huggingface.co/docs/huggingface_hub/package_reference/file_download).
- HEAD on resolve with `Accept-Encoding: identity` returns X-Repo-Commit, X-Linked-Etag (= sha256 for LFS), X-Linked-Size, Location. Full spec at https://huggingface.co/.well-known/openapi.json.
- [FC] Verified anonymously on https://huggingface.co/baidu/Unlimited-OCR/resolve/07dea832e22aefee32ad281d4b80551282e1c168/model-00001-of-000001.safetensors: HEAD returns 302 with X-Repo-Commit 07dea83…, X-Linked-Size 6672547120, X-Linked-ETag = sha256 2bc48a7a…855fc6; redirect goes to the Xet bridge (xet hash 56e1945a…); ranged GET returned 206 and the safetensors header.
- [FC] ModelScope mirror `PaddlePaddle/Unlimited-OCR` (License "mit", public, no login, 136,436 downloads, 136,471 at re-check): **identical weights and model files, not a byte-identical repo**. Verified identical by sha256: weights (2bc48a7a…855fc6, 6,672,547,120 B), LICENSE (d985048c…), modeling_unlimitedocr.py, modeling_deepseekv2.py, deepencoder.py, configuration_deepseek_v2.py, conversation.py. Different: `.gitattributes` 2,308 B vs 302 B on HF, plus extra `configuration.json` (76 B) (https://www.modelscope.cn/api/v1/models/PaddlePaddle/Unlimited-OCR/repo/files?Revision=master&Recursive=true, https://www.modelscope.cn/api/v1/models/PaddlePaddle/Unlimited-OCR, https://modelscope.cn/models/PaddlePaddle/Unlimited-OCR).
- ModelScope files served at `https://www.modelscope.cn/models/PaddlePaddle/Unlimited-OCR/resolve/master/<file>` (verified with config.json). `resolve/master` is not commit-pinned, so the app's own sha256 check is mandatory on this path. `.../api/v1/models/baidu/Unlimited-OCR` → 404.
- [FC] ModelScope Range support **confirmed** [C]: ranged GET on https://www.modelscope.cn/models/PaddlePaddle/Unlimited-OCR/resolve/master/model-00001-of-000001.safetensors returned 302 → cdn-lfs-cn-1.modelscope.cn → "206 Partial Content", `Content-Range: bytes 100-199/6672547120`, `Accept-Ranges: bytes`; HEAD returns X-Linked-Etag = the sha256. A ranged request on the small config.json returned 200 (with only 50 bytes), so small files behave differently. Resume from a large offset was not tested.
- ModelScope SDK `snapshot_download` exists (https://raw.githubusercontent.com/modelscope/modelscope/master/modelscope/hub/snapshot_download.py); integrity behaviour [U].
- hf-mirror.com: third-party (China, "padeoe") mirror via `HF_ENDPOINT=https://hf-mirror.com` (https://hf-mirror.com/). Not operated by HF or Baidu. GhostCorp uses it as automatic fallback.
- [FC] **hf-mirror.com is not an independent fallback from this machine.** From the Czech Republic every request for this repo returns "308 Permanent Redirect" (Server: Caddy) back to huggingface.co: tested on https://hf-mirror.com/baidu/Unlimited-OCR/resolve/07dea832e22aefee32ad281d4b80551282e1c168/config.json, the safetensors, and https://hf-mirror.com/api/models/baidu/Unlimited-OCR. If huggingface.co is down, hf-mirror.com fails the same way. May be geo-dependent (may still proxy for Chinese IPs). Real independent fallback = ModelScope. [C]
- GitHub Releases: "Each file included in a release must be under 2 GiB"; up to 1000 assets per release, no limit on total size or bandwidth (https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). 6,672,547,120 B / 2 GiB = 3.11, so an own mirror needs the shard split into ≥4 parts plus manifest.

**Version lock**
- transformers 4.57.1 forces `huggingface-hub<1.0,>=0.34.0`, the 0.3x line (0.36.0 uploaded 2025-10-23, https://pypi.org/pypi/huggingface_hub/0.36.0/json). [FC] Newest release satisfying the bound: **0.36.2, released 2026-02-06** (0.36.1: 2026-02-02) (https://pypi.org/pypi/huggingface_hub/json). [C]
- Not available on hub <1.0: `hf cache verify` / `HfApi.verify_repo_checksums` (added v1.1.0, PR #3461; https://github.com/huggingface/huggingface_hub/pull/3461, https://github.com/huggingface/huggingface_hub/releases/tag/v1.1.0, https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/cli/cache.py, https://huggingface.co/docs/huggingface_hub/package_reference/cli), `IncompleteSnapshotError`, `trees/` cache, `dry_run` (confirmed absent from v0.36.2 file_download.py and _snapshot_download.py), `resolve_revision`.
- [FC] **Also not available on 0.36.x: `HF_HUB_DISABLE_SYMLINKS`.** In v0.36.2 constants.py only `HF_HUB_DISABLE_SYMLINKS_WARNING` is defined; the v0.36.0 env-var docs do not list it. It exists only on main (constants.py line 279). Setting it under the pin is a silent no-op (https://raw.githubusercontent.com/huggingface/huggingface_hub/v0.36.2/src/huggingface_hub/constants.py, https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/constants.py). [C]
- Available on 0.36.x: `local_dir` + `.cache/huggingface` metadata, `HF_HUB_OFFLINE`, `local_files_only`, `HF_HUB_DISABLE_XET`, `HF_HUB_DISABLE_SYMLINKS_WARNING`, `HF_HUB_ETAG_TIMEOUT` / `HF_HUB_DOWNLOAD_TIMEOUT`, `hf download` CLI (since 0.34.0), `try_to_load_from_cache`. Uses `requests`.
- Conflict: three angles recommend `hf cache verify`, `dry_run=True` and `IncompleteSnapshotError`. Those are hub 1.x/2.x features and unusable under the pin. On 0.3x an incomplete snapshot was "returned silently". The app must do its own completeness and hash checks.
- [FC] On 0.36.2 `snapshot_download` returns an existing non-empty `local_dir` with only a warning when the Hub is unreachable (https://raw.githubusercontent.com/huggingface/huggingface_hub/v0.36.2/src/huggingface_hub/_snapshot_download.py).

**Cache mechanics** [C]
- Default Windows cache `C:\Users\<user>\.cache\huggingface\hub`. Priority `HF_HUB_CACHE` > `HF_HOME` (`$HF_HOME/hub`) > `XDG_CACHE_HOME`; per call `cache_dir=`.
- `HF_HOME` also holds token, modules, xet (`HF_XET_CACHE`), assets (`HF_ASSETS_CACHE`). `TRANSFORMERS_CACHE` and `HUGGINGFACE_HUB_CACHE` are deprecated.
- Sources: https://huggingface.co/docs/transformers/installation, https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables, https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables, https://huggingface.co/docs/huggingface_hub/v0.36.0/en/package_reference/environment_variables.
- All HF env vars are read at import time. Set them in the entry script before any `import transformers` or `huggingface_hub`.
- Layout: `models--baidu--Unlimited-OCR/{blobs,refs,snapshots}` (+ `trees/<commit>.json`, `CACHEDIR.TAG`, `.no_exist/` in v2). Blobs named by etag. Snapshot files are relative symlinks. Locks in `<cache>/.locks/<repo>/<etag>.lock` (https://huggingface.co/docs/hub/local-cache).
- Windows without Developer Mode or admin (true on the target PC): degraded mode, real files in `snapshots/`, `blobs/` unused, warning printed. `HF_HUB_DISABLE_SYMLINKS_WARNING=1` silences. [FC] There is no way to force no-symlink mode by env var on 0.36.x. Code fallback: `try: os.symlink(...) except (FileExistsError, PermissionError): shutil.move(...)`. No disk penalty for one pinned revision (https://huggingface.co/docs/huggingface_hub/guides/manage-cache, https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache).
- `local_dir=` mode: plain files + `.cache/huggingface/` metadata (3 lines per file: commit_hash, etag, timestamp; discarded if file missing or mtime differs by >1 s). Never uses symlinks (https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/_local_folder.py, https://raw.githubusercontent.com/huggingface/huggingface_hub/v0.36.2/src/huggingface_hub/_local_folder.py).
- Self-heal: a copied folder is re-hashed (tens of seconds for 6.7 GB), not re-downloaded.
- [FC] Partial-file location on 0.36.x resolved [C]: local_dir mode writes `<local_dir>/.cache/huggingface/download/<short_hash>.<etag>.incomplete` (_local_folder.py lines 87–89); cache mode writes `Path(blob_path + ".incomplete")` (file_download.py line 1176). The `<blob>.<uuid8>.incomplete` naming exists only on main (file_download.py line 2003).
- Zero-network fast path: `local_dir` + full 40-char commit hash (regex `^[0-9a-f]{40}$`) returns immediately when file exists and `local_metadata.commit_hash == revision`. 7-char hashes are rejected. With `revision='main'` every call does a HEAD (`HF_HUB_ETAG_TIMEOUT` 10 s, then falls back to cache) (https://raw.githubusercontent.com/huggingface/huggingface_hub/main/src/huggingface_hub/file_download.py, https://raw.githubusercontent.com/huggingface/huggingface_hub/v0.36.2/src/huggingface_hub/file_download.py).
- `HF_HUB_OFFLINE=1` blocks all Hub HTTP. Loading from a local directory never contacts the Hub (`if os.path.isdir(path_or_repo_id): return existing_files`) (https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/utils/hub.py, https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/utils/hub.py).
- Long paths: huggingface_hub uses `\\?\` extended paths. Keep the app dir short anyway.

**Integrity: verify it yourself** [C]
- HTTP path (0.36.x): streams to the `.incomplete` file named above, resumes with Range, retries 5×, checks size only ("Consistency check failed: file should be of size ..."). No sha256.
- `_check_disk_space` only warns. The app must enforce free space.
- Xet path: `xet_get(...)` then `_chmod_and_move`. No size or hash verification in huggingface_hub.
- xet-core PR #967 (post-download hash check) was closed without merging on 2026-09-17 ("I don't think we want this feature") (https://github.com/huggingface/xet-core/pull/967). Web summaries claiming it is on by default are wrong.
- Motivating bug: huggingface_hub #3643 (closed), same file hashed to four different values across runs (https://github.com/huggingface/huggingface_hub/issues/3643).
- The safetensors is Xet-stored, so the default download goes through hf_xet unless `HF_HUB_DISABLE_XET=1` or hf_xet is missing (fallback warning printed).
- hf_xet 1.6.0 (2026-08-03) ships `hf_xet-1.6.0-cp38-abi3-win_amd64.whl` (4,033,128 B, 4.0 MB) and win_arm64; no 32-bit wheel (https://pypi.org/project/hf-xet/#files, https://pypi.org/pypi/hf-xet/json). hub 0.36.0 depends on `hf-xet<2.0.0,>=1.1.3`; hub 2.0.0 on `>=1.6.0`. Bundled since hub 0.32.0.
- `HF_XET_HIGH_PERFORMANCE` is "intended for machines with high bandwidth and at least 64 GB of RAM". `HF_XET_RECONSTRUCT_WRITE_SEQUENTIALLY` for HDDs.
- [FC] Chunk cache resolved [C]: for hf_xet 1.6.0 (what pip resolves under the pin) the cache is **disabled by default**. `hf_xet/Cargo.toml` default features include "no-default-cache"; the Hub docs state the Python package ships with it disabled (`HF_XET_CHUNK_CACHE_SIZE_BYTES=0`). The 10 GB figure in the v0.36 docs is stale for that wheel (https://raw.githubusercontent.com/huggingface/xet-core/v1.6.0/hf_xet/Cargo.toml, https://raw.githubusercontent.com/huggingface/xet-core/v1.6.0/xet_runtime/src/config/groups/chunk_cache.rs, https://huggingface.co/docs/hub/xet/using-xet-storage). An older hf_xet with the cache on could need several more GB in `HF_XET_CACHE`.
- hf_transfer (`HF_HUB_ENABLE_HF_TRANSFER=1`) is deprecated and "lacks … resumable downloads and proxies".

**Xet stalls on Windows** [L, mostly titles and snippets]
- xet-core #446 (Windows deadlock; [FC] its title does not mention ReFS; https://github.com/huggingface/xet-core/issues/446), huggingface_hub #3429 (Ctrl+C hang), #4508 (Jul 2026, hangs 80%+), #4520 (Jul 2026), xet-core #789/#850 (stall after 16–200 MB). [FC] All exist and all are now **closed**.
- Blog (hub 1.x, Python 3.13, RTX 5090): `snapshot_download` hung at "Fetching 3 files: 0%"; per-file `hf_hub_download` with `HF_HUB_DISABLE_XET=1` ran at ~314 MB/s (https://ai-muninn.com/en/blog/huggingface-download-stuck-zero-bytes-windows-ai-toolkit).
- Workaround: `HF_HUB_DISABLE_XET=1`. Because env is captured at import, retry in a fresh subprocess.

**Remote-code cache** [C]
- `trust_remote_code` copies the `.py` files into `HF_MODULES_CACHE` (default `$HF_HOME/modules`) under `transformers_modules/...`, creates `__init__.py`, appends to `sys.path`. Relative imports resolved recursively (https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/dynamic_module_utils.py lines 91–97; hub.py line 103; https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/dynamic_module_utils.py).
- [FC] Folder naming on 4.57.1 resolved [C]: Hub loads use `<repo>/<commit hash>/`. **Local directory loads use `transformers_modules/<sanitized basename of the folder>/` with no hash subfolder.** Files are re-copied whenever `filecmp` says they differ, so a patched modeling file is picked up automatically. Two model folders with the same basename share one module cache folder and would collide.
- Must be writable at runtime. Keep it in `%LOCALAPPDATA%`, never inside the PyInstaller bundle.
- `if is_offline_mode() and not local_files_only: local_files_only = True`.

**Recommended approach**
1. Entry script sets env before HF imports: `HF_HOME=<app>\hf_home`, `HF_HUB_DISABLE_SYMLINKS_WARNING=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `HF_HUB_DISABLE_PROGRESS_BARS=1`; point `HF_XET_CACHE` inside the app dir. [FC] Note: a llama.cpp fallback engine would write `-hf` downloads into the same `hf_home\hub` (section 7).
2. Download into an app-owned plain folder, e.g. `%LOCALAPPDATA%\<App>\models\unlimited_ocr` (no dots, dashes or spaces), not the hub cache.
3. Pin `revision='07dea832e22aefee32ad281d4b80551282e1c168'`. Bump only with an app release.
4. Skip junk: `ignore_patterns=['assets/*','wheel/*','*.pdf','*.gif','.gitattributes']`, or `allow_patterns=['*.json','*.py','*.safetensors','*.md','LICENSE']`.
5. Pre-check free space (pattern uses ≥8 GB; GhostCorp reserves 20 GiB on the system drive). [FC] 8 GB is thin: payload is 6.68 GB, the `.incomplete` file is written inside the target folder then moved, and `_check_disk_space` only warns. Consider ≥10 GB. [L, inference]
6. After download, sha256-verify the shard once against `2bc48a7a…855fc6`. Later starts use a fast manifest check (commit + file sizes).
7. Write the ready marker (`manifest.json`) only after verification.
8. Load with absolute path + `local_files_only=True`.
9. [FC] Fallback ladder: hf_xet → fresh subprocess with `HF_HUB_DISABLE_XET=1` → plain HTTPS Range downloader against HF resolve → **ModelScope** (Range confirmed, sha256 check mandatory) → hf-mirror.com last (redirects to HF from the Czech Republic, no redundancy).
10. [FC] Keep Baidu's MIT LICENSE in the model folder, add the Apache-2.0 licence text and a third-party notices file; mark any patched file as modified.

Code pattern from the download research (https://huggingface.co/docs/huggingface_hub/guides/download). `_ignored` was undefined in the original and is added here; all of it is untested.

```python
# bootstrap.py  (runs BEFORE importing huggingface_hub/transformers)
import os, pathlib
APP = pathlib.Path(os.environ['LOCALAPPDATA']) / 'UnlimitedOcrApp'   # short, no dots/spaces
MODEL_DIR = APP / 'models' / 'unlimited_ocr'
os.environ.setdefault('HF_HOME', str(APP / 'hf_home'))
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
# os.environ.setdefault('HF_HUB_DISABLE_XET', '1')   # set on retry after a stall
# HF_HUB_DISABLE_SYMLINKS does not exist on hub 0.36.x -> do not rely on it

# downloader.py
import hashlib, json, shutil, fnmatch
from huggingface_hub import snapshot_download, HfApi
REPO = 'baidu/Unlimited-OCR'
COMMIT = '07dea832e22aefee32ad281d4b80551282e1c168'
IGNORE = ['assets/*', 'wheel/*', '*.pdf', '*.gif', '.gitattributes']
MANIFEST = MODEL_DIR / 'manifest.json'
def _ignored(path): return any(fnmatch.fnmatch(path, p) for p in IGNORE)

def fetch_manifest():
    files = HfApi().list_repo_tree(REPO, revision=COMMIT, recursive=True)
    return {f.path: {'size': f.size, 'sha256': (f.lfs.sha256 if getattr(f, 'lfs', None) else None)}
            for f in files if hasattr(f, 'size') and not _ignored(f.path)}

def sha256_of(p, bufsize=8 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(bufsize), b''):
            h.update(chunk)
    return h.hexdigest()

def is_ready(deep=False):
    if not MANIFEST.exists(): return False
    m = json.loads(MANIFEST.read_text())
    if m.get('commit') != COMMIT: return False
    for rel, info in m['files'].items():
        p = MODEL_DIR / rel
        if not p.is_file() or p.stat().st_size != info['size']: return False
        if deep and info['sha256'] and sha256_of(p) != info['sha256']: return False
    return True

def ensure_model(progress_cb=None):
    if is_ready(): return MODEL_DIR
    free = shutil.disk_usage(MODEL_DIR.parent if MODEL_DIR.parent.exists() else APP).free
    if free < 8 * 1024**3: raise RuntimeError('need >=8 GB free')   # thin; consider 10 GB
    files = fetch_manifest()
    snapshot_download(REPO, revision=COMMIT, local_dir=str(MODEL_DIR), ignore_patterns=IGNORE,
                      max_workers=2, etag_timeout=30)
    bad = [rel for rel, i in files.items() if i['sha256'] and sha256_of(MODEL_DIR / rel) != i['sha256']]
    if bad:
        for rel in bad: (MODEL_DIR / rel).unlink()
        snapshot_download(REPO, revision=COMMIT, local_dir=str(MODEL_DIR), allow_patterns=bad, force_download=True)
        if any(sha256_of(MODEL_DIR / rel) != files[rel]['sha256'] for rel in bad): raise RuntimeError('corrupt download')
    MANIFEST.write_text(json.dumps({'commit': COMMIT, 'files': files}))
    return MODEL_DIR
```

- [FC] `list_repo_tree` / `RepoFile.lfs.sha256` on hub 0.36.x: **confirmed** [C]. `BlobLfsInfo` is a dataclass(dict) with fields size, sha256, pointer_size, so both `f.lfs.sha256` and `f.lfs["sha256"]` work (https://raw.githubusercontent.com/huggingface/huggingface_hub/v0.36.2/src/huggingface_hub/hf_api.py line 336).
- CLI equivalent (0.34+): `hf download baidu/Unlimited-OCR --revision 07dea83… --local-dir <dir> --exclude 'assets/*' --exclude 'wheel/*'`.
- Per-file loop: `for rel in manifest: hf_hub_download(REPO, rel, revision=COMMIT, local_dir=MODEL_DIR)`.
- Xet-off retry: `subprocess.run([sys.executable, '-m', 'app.downloader'], env={**os.environ, 'HF_HUB_DISABLE_XET': '1'})`. In a frozen build use the exe with a `--download` flag.

Plain-HTTPS fallback [L, untested; FC: source order changed]:

```python
import requests, os
SOURCES = [
  'https://huggingface.co/baidu/Unlimited-OCR/resolve/{commit}/{path}',
  'https://www.modelscope.cn/models/PaddlePaddle/Unlimited-OCR/resolve/master/{path}',  # Range OK on the big file (206); NOT commit-pinned -> sha256 mandatory
  'https://hf-mirror.com/baidu/Unlimited-OCR/resolve/{commit}/{path}',                  # from CZ: 308 redirect to huggingface.co, no redundancy
]
def http_download(url, dest, expected_size, expected_sha256=None, chunk=8<<20):
    part = dest.with_suffix(dest.suffix + '.part')
    have = part.stat().st_size if part.exists() else 0
    headers = {'Accept-Encoding': 'identity'}
    if have: headers['Range'] = f'bytes={have}-'
    with requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=(10, 60)) as r:
        if have and r.status_code == 200: have = 0; mode = 'wb'   # server ignored Range -> restart
        elif r.status_code == 206: mode = 'ab'
        else: r.raise_for_status(); mode = 'wb'
        with open(part, mode) as fh:
            for b in r.iter_content(chunk):
                fh.write(b); have += len(b)
    if have != expected_size: raise OSError(f'size {have} != {expected_size}')
    if expected_sha256 and sha256_of(part) != expected_sha256: part.unlink(); raise OSError('sha256 mismatch')
    os.replace(part, dest)
```

**Windows pitfalls**
- Patched modeling file vs download folder: a patched `modeling_unlimitedocr.py` no longer matches local_dir metadata, so `snapshot_download` would overwrite it. The manifest size check above would also flag it as not ready. Keep pristine download and patched runtime copy separate, or exclude patched files from the check and never re-run the download once ready. [L, design inference] [FC] Give the pristine and patched folders **different basenames**, because local-dir remote code is cached by basename only.
- [FC] Relative or dotted model path: the `ModuleNotFoundError: No module named 'transformers_modules.'` failure (https://github.com/huggingface/transformers/issues/29251; PRs #29175/#29262) is **outdated for 4.57.1**. `_sanitize_module_name()` rewrites "." to "_dot_" and "-" to "_hyphen_" and prefixes a leading digit with "_" (dynamic_module_utils.py lines 51–70, 394–398). An absolute, plain folder name is still sensible hygiene, not a hard requirement. [C]
- Offline trust_remote_code was historically broken (issue #34855, 4.46.3). [FC] PR #37716 (merged 2025-05-26, https://github.com/huggingface/transformers/pull/37716) **is included in 4.57.1** [C]: merge commit ba6d7222 is an ancestor of tag v4.57.1 (ahead 1408, behind 0). PR #36808 is still open (https://github.com/huggingface/transformers/pull/36808). Keep all `.py` next to `config.json`.
- Paging file: mmap load of large safetensors can fail with `OSError ... (os error 1455)` (https://github.com/Comfy-Org/ComfyUI/issues/15424, OmniGen #181). Unlikely with 64 GB. [FC] `disable_mmap` exists in 5.17 docs but is **absent from 4.57.1** (zero matches in v4.57.1 modeling_utils.py; docs page https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/model). It cannot be the error-1455 workaround under the pin. [C]
- Do not instantiate the model during setup. Wasihub1 fixed a "model-loading crash during setup" by downloading only.
- Avoid hashing at every boot. unlocr PR #3 fixed a 100% CPU startup hang from exactly that.
- Default timeouts are 10 s; raise `HF_HUB_DOWNLOAD_TIMEOUT` on slow links.
- No upstream issue mentions weight download or caching problems.

---

## 7 Packaging options

**Component sizes** [C unless noted; all byte counts re-measured and matched]

| Component | Download | Unpacked / notes |
|---|---|---|
| torch 2.10.0+cu128 cp311 win_amd64 | 2,867,372,330 B (2.87 GB) | 4,526,140,019 B (4.53 GB), 11,756 files |
| torch 2.10.0+cu126 cp311 | 2,589,850,483 B (2.59 GB) | n/a |
| torch 2.10.0+cu130 cp311 | 1,867,358,588 B (1.87 GB) | 2,768,972,067 B (2.77 GB) |
| torch 2.10.0+cpu cp311 | 113,636,478 B (0.11 GB); PyPI 113,723,116 B (113.7 MB) | 424,455,367 B (0.42 GB) |
| torchvision 0.25.0 | cu128 9,367,831 B (9.4 MB); cpu 4,038,833 B (4.0 MB) | n/a |
| Weights (bf16) | 6.67 GB | never bundle |
| uv 0.12.19 (2026-09-25) | 17,955,780 B = 18.0 MB (17.1 MiB) [FC, sheet said 17 MB] | n/a |
| cpython 3.12.14+20260924 install_only_stripped | 22,052,624 B (22 MB); full 46,462,396 B (46 MB) | 3.11.16 stripped 25,273,229 B (25 MB) |
| python-3.11.9-embed-amd64.zip | 11,249,023 B | 3.12.10: 11,133,606 B |
| llama.cpp b11221 win cuda-13.4 | 153,535,785 B + cudart 423,535,356 B (423.5 MB) | ≈0.6 GB |
| llama.cpp b11221 win cuda-12.4 | 264,519,230 B + cudart 391,443,627 B | n/a |
| llama.cpp b11221 win vulkan / cpu | 33,062,713 B / 19,156,577 B | rocm 257 MB, sycl 121 MB, openvino 88 MB |
| focr-x86_64-pc-windows-msvc.exe v0.9.0 | 25,603,072 B | + 4,157,448,783 B weights |

- Wheel sources: https://download.pytorch.org/whl/cu128/torch-2.10.0%2Bcu128-cp311-cp311-win_amd64.whl, https://download.pytorch.org/whl/cu126/torch-2.10.0%2Bcu126-cp311-cp311-win_amd64.whl, https://download.pytorch.org/whl/cu130/torch-2.10.0%2Bcu130-cp311-cp311-win_amd64.whl, https://download.pytorch.org/whl/cpu/torch-2.10.0%2Bcpu-cp311-cp311-win_amd64.whl. Other sources: https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip, https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip, https://api.github.com/repos/astral-sh/uv/releases/latest, https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest, https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11221, https://api.github.com/repos/Dicklesworthstone/franken_ocr/releases/tags/v0.9.0.
- Largest cu128 DLLs, all in `torch/lib`: torch_cuda.dll 908 MB, cublasLt64_12.dll 675 MB, cudnn_engines_precompiled64_9.dll 514 MB, cusparse64_12.dll 380 MB, cudnn_adv64_9.dll 282 MB, cufft64_11.dll 276 MB, torch_cpu.dll 265 MB, cusolver64_11.dll 226 MB.
- cu130: cublasLt64_13.dll 478 MB, torch_cuda.dll 409 MB, cufft64_12.dll 284 MB, torch_cpu.dll 265 MB.
- Windows wheels have no nvidia-* pip deps; Requires-Dist is only filelock, typing-extensions, sympy, networkx, jinja2, fsspec (+ setuptools on py≥3.12). Linux manylinux wheel is 915,607,863 B (915.6 MB).
- [FC] Available torch versions with win_amd64 wheels (measured 2026-09-27): cu126 2.6.0–2.14.0; cpu up to 2.14.0; cu128 2.7.0–2.11.0; cu130 2.9.0, 2.9.1, 2.10.0, 2.11.0, 2.12.0, 2.12.1, 2.13.0, 2.14.0; cu129 2.8.0 and 2.9.0 only. (Sheet previously said cu126 and cpu 2.10.0–2.13.0 and cu128 only 2.10.0, 2.11.0.) An earlier truncated fetch of /whl/cpu showing ≤2.1.2 should be disregarded.
- llama.cpp releases: https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=3. Several per day (b11222 was published 2026-09-27 17:43 UTC). `/releases/latest` resolves to an odd `v0.5.0` tag (https://api.github.com/repos/ggml-org/llama.cpp/releases/latest); use `bNNNNN` tags.

**Driver and architecture gates**
- NVIDIA release notes (https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html): CUDA 12.6.x needs Windows driver ≥560.76 (Linux ≥560.28.03); 12.8.x ≥570.65 (Linux ≥570.26); 12.9.x ≥576.02 (Linux ≥575.51.03); 13.0.x ≥580. Minor-version floor 12.x ≥525, 13.x ≥580. [C, re-checked]
- uv's table uses looser minor-compat floors: Windows cu130/cu132 ≥580; cu129/cu128/cu126 ≥528.33; Linux cu130 ≥580, cu129..cu120 ≥525.60.13.
- GhostCorp's table: ≥580 → 13.0, ≥575 → 12.9, ≥570 → 12.8, ≥560 → 12.6, ≥550 → 12.4, ≥535 → 12.2, ≥525 → 12.0.
- The three tables differ because of CUDA minor-version compatibility. Any of them admits the target's 617.14.
- PyTorch kernels: cu128 builds from 2.8 dropped Maxwell (sm_50) and Pascal (sm_60). 2.11 dropped Volta (sm_70) from cu128/cu129 (cuDNN 9.15.1). cu126 carries kernels up to sm_90. [FC] **PyTorch 2.14 is the last release with cu126 / CUDA 12.x wheels**; publishing stops in 2.15 (nightly removal from 2026-09-07); afterwards only CUDA 13.x, covering Turing (sm_75) through Blackwell. [L]
- Sources: https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432, https://dev-discuss.pytorch.org/t/cuda-toolkit-version-and-architecture-support-update-maxwell-and-pascal-architecture-support-removed-in-cuda-12-8-and-12-9-builds/3128.
- [FC] The quote "CUDA 13.0 is now the stable default and CUDA 12.6 remains available for users on older drivers", attributed to the PyTorch 2.10 blog, conflicts with PyPI metadata: torch 2.10.0 requires `nvidia-cuda-runtime-cu12==12.8.90` (Linux), so the 2.10 default build is CUDA 12.8. The cu12 pins disappear only in 2.11.0; the quote most likely belongs to 2.11 (https://pypi.org/pypi/torch/2.10.0/json, https://pypi.org/pypi/torch/2.11.0/json). [U attribution]
- Practical rule: compute_cap ≥8.0 → cu130 (driver ≥580) or cu128; 7.5 → cu128/cu130 with fp16, not bf16 ("bfloat16 arithmetic is an Ampere-and-up feature (sm_80)"); 6.x/5.x → cu126 + torch 2.10 or CPU.

**GPU detection without torch** [C, local probe]
- `nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader` returned "NVIDIA GeForce RTX 4080 SUPER, 617.14, 16376 MiB, 8.9". `nvidia-smi.exe` and `nvml.dll` are in `C:\Windows\System32`. [FC] Also query `memory.used` / `memory.free`: 10,961 MiB was in use at probe time.
- `compute_cap` is missing on old drivers (absent on 470.182.03, present on 510+). Parse defensively and fall back to a name→sm table.
- WMI `Win32_VideoController`: PNPDeviceID `VEN_10DE` = NVIDIA. `AdapterRAM` is uint32 and saturates at 4,293,918,720 B (observed). DriverVersion `32.0.16.1714` = 617.14 (last 5 digits).
- 64-bit VRAM in registry: `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\<000N>\HardwareInformation.qwMemorySize` = 17,171,480,576 on the target. Also documented in Mesh-LLM/mesh-llm PR #1836 and 4DA PR #733.
- `nvidia-ml-py` (PyPI 13.615.71) can query NVML without torch.
- uv: `uv pip install torch --torch-backend=auto` (or `UV_TORCH_BACKEND=auto`); values auto, cpu, cu118, cu126, cu128, cu130, rocm7.2, xpu; only in the `uv pip` interface. Detection order: `UV_CUDA_DRIVER_VERSION`, `/sys/module/nvidia/version`, `/proc/driver/nvidia/version`, then `nvidia-smi` (https://docs.astral.sh/uv/guides/integration/pytorch/). "auto" does not know about sm_xx kernel drops.

**Options and trade-offs**

| Option | Shipped size | First-run download | Pros | Cons |
|---|---|---|---|---|
| A. PyInstaller onedir with CUDA torch | ≈4.6–5 GB (cu128) or ≈3.0–3.3 GB (cu130) [L] | weights 6.67 GB | one stack, same as Wolfie | every build carries CUDA DLLs; exceeds installer limits; CPU machines carry dead weight |
| A'. PyInstaller onedir, CPU torch | ≈0.6–0.8 GB [L] | weights 6.67 GB | small | CPU only, about a minute to minutes per page |
| A''. PyInstaller onefile with torch | n/a | n/a | n/a | re-extracts gigabytes to `_MEIxxxxxx` on every launch; not viable |
| B. Small launcher + bootstrapped engine (uv + python-build-standalone + venv) | launcher small (Wolfie onefile ~116 MB; Tauri precedents 2.7–5.3 MB) | uv 18 MB + Python 22–25 MB + torch 1.87–2.87 GB + deps + weights 6.67 GB; GhostCorp: "about 10 GB", "~16 GB of free disk" | picks torch index per GPU; launcher hash rarely changes; all three wrappers chose this | more moving parts; VC++ redist check advisable; network at first run |
| C. python.org embeddable zip + pip | 11.2 MB | as B | official | "pip ... is not supported with this distribution"; `._pth` fiddling; CPython #102169 (3.11 ignoring `import site`) |
| D. PyApp (Rust launcher) | small | as B | built-in `self update / remove / restore`; can embed Python | cannot pick torch index by GPU itself [L] |
| E. llama.cpp + GGUF | ≈0.6 GB CUDA runtime or 19 MB CPU | Q8_0 3.13 GB + mmproj 0.81–0.83 GB [FC] | torch-free, prebuilt Windows CUDA/Vulkan/CPU binaries | mainline = full MHA, single-page only; R-SWA PR #24975 unmerged; [FC] MHA vs R-SWA measured once on BF16: CER 0.7792% vs 0.3344% |
| F. franken_ocr (focr.exe) | 25.6 MB | 4.16 GB int8 | no Python, no GPU | CPU only; int8 not reference quality; open AVX2 multi-page bug #17; licence unclear; no x86 speed data |
| G. ONNX / OpenVINO | n/a | 6.04 GB / 12.25 GB | n/a | not an end-to-end path (below) |
| H. Nuitka | ~2x PyInstaller folder [U] | n/a | faster start | multi-minute compiles; size is the CUDA DLLs anyway (https://coderslegacy.com/nuitka-vs-pyinstaller/) |

**Size limits**
- EXE installer with embedded resources ≤4 GB; MSI ≤2 GB, as quoted by Advanced Installer. Inno Setup offers disk spanning. A single self-contained CUDA installer is not feasible (https://advancedinstaller.com/user-guide/qa-installer-large-resources.html; page now lives at https://docs.advancedinstaller.com/qa-installer-large-resources.html). [L]

**PyInstaller specifics**
- [FC] https://github.com/orgs/pyinstaller/discussions/8552: "the torch library in the app is about 4GB" is the **question-asker's** sentence, quoted back by maintainer rokm. rokm's own statements: onefile with torch 2.3+cu118 "comes out at 2.6GB"; CUDA/cuDNN libs "cannot be split"; small exes use CPU-only torch. [L]
- Docs: "It is much easier to diagnose problems in one-folder mode".
- hook-torch.py collects torch dynamic libs, submodules, data files (excluding *.h/*.hpp/*.cuh/*.lib/*.cpp/*.pyi/*.cmake), plus MKL DLLs on Windows. hook-transformers.py collects metadata for every dependency and sets `module_collection_mode='pyz+py'` (needs PyInstaller ≥5.3) (https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/master/_pyinstaller_hooks_contrib/stdhooks/hook-torch.py, https://raw.githubusercontent.com/pyinstaller/pyinstaller-hooks-contrib/master/_pyinstaller_hooks_contrib/stdhooks/hook-torch.py, https://raw.githubusercontent.com/pyinstaller/pyinstaller-hooks-contrib/master/_pyinstaller_hooks_contrib/stdhooks/hook-transformers.py). [C]
- Versions: PyInstaller 6.22.3 (https://pypi.org/pypi/pyinstaller/json), hooks-contrib 2026.7; target has 6.21.0. PyInstaller 6.14.0 fixed transformers pipeline issue #9134.
- Known problems: #7646 (needs `--collect-all transformers` / `copy_metadata`, https://github.com/pyinstaller/pyinstaller/issues/7646), #5672 "OSError: Can't get source", old `caffe2_nvrtc.dll` WinError 126 (discuss.pytorch.org 181134), `torch.cuda.is_available()` False inside dist (#2956). `copy_metadata` for huggingface_hub, tokenizers, safetensors, torch commonly needed. [U list]
- No primary report of PyInstaller + trust_remote_code failing. Should work if `HF_MODULES_CACHE` is a writable real directory and all imported transformers/torch symbols are collected. [U by direct test]
- "Split archive" technique: app core + "~2 GB NVIDIA runtime layer" with sha256 sidecars; "In torch 2.10+ the NVIDIA DLLs moved from nvidia/ subdirs to _internal/torch/lib/" (https://skills.lc/kjuhwa/skills-hub/kjuhwa-skills-hub-skills-build-tooling-pyinstaller-cuda-onedir-split-archive-skill-md). [L]
- Startup: no reliable Windows numbers. "5-10 second lag from importing torch"; first import on a fresh PC ~1 minute; CUDA init adds seconds (https://github.com/orgs/pyinstaller/discussions/8970, #9080). [U] Load torch and the model in a background worker after the window is up.
- [FC] VC++ redistributable: torch 2.9.0/2.9.1/2.10-dev `OSError: [WinError 1114] ... Error loading torch_python.dll` (https://github.com/pytorch/pytorch/issues/169429, still OPEN). The reporter says installing MSVC++ 14 x64 Redistributable 14.50.35719 fixed it, but the error did not return after uninstalling it again, and writes "I am not sure whether installing the latest supported redistributable is the correct solution". The fix is **not established**. [U]

**Bootstrap building blocks** [C unless noted]
- uv: `uv python install 3.12`; `UV_PYTHON_INSTALL_DIR`, `UV_PYTHON_INSTALL_MIRROR`, `UV_CACHE_DIR`, `UV_OFFLINE`, `UV_NO_CACHE`; `uv venv --python 3.12 <dir>`; `uv pip install --python <venv>\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu130 torch==2.10.0 torchvision==0.25.0` (https://docs.astral.sh/uv/reference/environment/). `uv venv --relocatable` is [U].
- python-build-standalone: "Portable, can be installed into any path".
- Embeddable package docs: https://docs.python.org/3.11/using/windows.html.
- Precedents: ComfyUI portable (`python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build`, run_nvidia_gpu.bat / run_cpu.bat; variants "CUDA 13.0 with Python 3.13" and "CUDA 12.6 with Python 3.12"); Comfy-Desktop ships relocatable Python with prebuilt GPU wheels; Pinokio bundles Miniforge; LM Studio downloads runtime extension packs into `%USERPROFILE%\.cache\lm-studio\extensions\backends` (https://github.com/lmstudio-ai/configs/blob/main/Extension-Pack-Instructions.md).
- PyApp: https://ofek.dev/pyapp/latest/runtime/, https://ofek.dev/pyapp/latest/config/distribution/. `PYAPP_PYTHON_VERSION` 3.7–3.14, `PYAPP_DISTRIBUTION_EMBED`, `PYAPP_DISTRIBUTION_SOURCE`, `PYAPP_FULL_ISOLATION`. [L]

**ONNX / OpenVINO are not viable** [C]
- Yehor/Unlimited-OCR (https://huggingface.co/Yehor/Unlimited-OCR) exports only the image-prefill graph ("does not export the Python generate() loop or PIL preprocessing"; fixed-length because MoE routing is data-dependent; dense MoE route can be slower; bf16 unsupported by ORT convs).
- Yehor/Unlimited-OCR-ONNX 6.04 GB (unlimited_ocr.onnx 4.0 GB + externals); Yehor/Unlimited-OCR-KV-Cache-ONNX 12.25 GB (prefill 4.0 GB + decode 2.4 GB + externals). Both 0 downloads, no cards.
- Export: `uv run --with onnx --with onnxscript python scripts/export_onnx.py --model . --image-sequence-length 512 --output onnx/unlimited_ocr.onnx`.
- No DirectML or ORT-GenAI build found.

**llama.cpp status**
- PR #24969 "mtmd: add unlimited-ocr (converter, full MHA)" merged 2026-06-24 (commit 894bb27; arch `unlimited-ocr`/`deepseek2-ocr`; single-page parity vs transformers 4.46.3) (https://github.com/ggml-org/llama.cpp/pull/24969, https://api.github.com/repos/ggml-org/llama.cpp/pulls/24969). [C]
- PR #25614 "fix max_tiles" merged 2026-08-05 (default 32, not DeepSeek-OCR's 9) (https://github.com/ggml-org/llama.cpp/pull/25614, https://api.github.com/repos/ggml-org/llama.cpp/pulls/25614). [C]
- PR #24975 "R-SWA reference sliding window attention" still OPEN (created 2026-06-24, updated 2026-09-25; branch sf/unlimited-ocr-rswa; single-page only) (https://github.com/ggml-org/llama.cpp/pull/24975, https://api.github.com/repos/ggml-org/llama.cpp/pulls/24975). [C]
- PR #24975 details: V cache defaults to F32 because "F16 garbles dense tables". CER: HF reference 0.1591, llama.cpp CUDA 0.1431, Metal 0.1658.
- Base PR #17400 (DeepSeek-OCR) merged 2026-03-25. Feature request https://github.com/ggml-org/llama.cpp/issues/25009.
- Conflict: GGUF cards (sabafallah: "only compatible with the PR branches"; sahilchachra: check out pull/24975) vs GitHub API merge status. API is better sourced; cards are stale. Mainline loads the GGUFs but runs full MHA.
- [FC] MHA vs R-SWA quality is **no longer unmeasured**: the vimalnakrani card measures BF16 overall CER 0.7792% (MHA) vs 0.3344% (R-SWA), 172.5 vs 168.2 tok/s. Mainline MHA therefore costs roughly 2x the CER on that test set. Single source. [C as reported]
- vimalnakrani requires commit 4fc4ec5 (build 168, 2026-07-01) or newer.
- Conflict on llama-server: vimalnakrani reports the multimodal path returns "Failed to tokenize prompt" (CLI only, that build). unlocr drives its own patched llama-server successfully. Version-dependent; test on the chosen build.
- Reference command: `llama-mtmd-cli -hf sabafallah/Unlimited-OCR-GGUF:bf16 --image x.jpeg -p "document parsing." --chat-template deepseek-ocr --temp 0 --flash-attn off -n 4096 -c 16384 --dry-multiplier 0.8 --dry-base 1.75`. PR #24975 adds `--repeat-penalty 1.0 --dry-allowed-length 35 --dry-penalty-last-n 128`.
- sahilchachra card: `winget install llama.cpp`, `llama serve -hf sahilchachra/Unlimited-OCR-GGUF:Q4_K_M`, `llama-server -m ... --mmproj ... -c 8192 --port 8080`, `--repeat-penalty 1.05`, `-n 4096+`. Its prompts (`<|grounding|>Convert the document to markdown.`, `Free OCR.`, `<|grounding|>Locate <|ref|>Text<|/ref|>`) are DeepSeek-style. Build recipe: `git fetch origin pull/24975/head:pr24975 && git checkout pr24975; cmake -B build -DCMAKE_BUILD_TYPE=Release; cmake --build build -j --target llama-mtmd-cli llama-server`.
- [FC] `-hf` download location for build b11221 is **not** `%LOCALAPPDATA%\llama.cpp`. Since commit 8c7957ca (2026-03-24, "common: add standard Hugging Face cache support", #20775) `common/hf-cache.cpp` resolves: `LLAMA_CACHE` > `HF_HUB_CACHE` > `HUGGINGFACE_HUB_CACHE` > `HF_HOME\hub` > `XDG_CACHE_HOME\huggingface\hub` > `%USERPROFILE%\.cache\huggingface\hub`, in HF `models--org--repo` layout (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11221/common/hf-cache.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/common.cpp). If the app sets `HF_HOME`, GGUFs land in the same `hf_home\hub`. Set `LLAMA_CACHE` explicitly. [C]
- llama-cpp-python: official CUDA wheels only cu121; prefer driving llama-server as a subprocess.
- Ollama: official support request #16938 (2026-06-27) open with no reply. A community import exists (https://ollama.com/frob/unlimited-ocr: latest/3b 6.7 GB, f16/q8_0/q4_K_M tags, 32K context, ~5k/4,966 pulls, `ollama run frob/unlimited-ocr:f16 'ocr [img]' /path/to/image.png`). Whether it implements R-SWA is not stated. LM Studio "will not load these until they update" per card. [U]
- HF blog "Using OCR models with llama.cpp" (2026-04-10, https://blog.ngxson.com/using-ocr-models-with-llama-cpp) does not list Unlimited-OCR. No ggml-org GGUF exists.
- Multi-page in GGUF: unsupported. [U]

**Code signing / SmartScreen** [C; FC: source citation corrected]
- Reputation mechanics: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation (ms.date 2026-05-04, updated 2026-08-17; contains no prices). Cost table, "Strong SmartScreen block", "Individuals: USA and Canada only", HSM since June 2023: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options (updated 2026-08-29). Azure FAQ: https://learn.microsoft.com/en-us/azure/artifact-signing/faq.
- Unsigned exe: "Strong SmartScreen block"; users click More info → Run anyway. Reputation is per file hash and does not transfer between unsigned versions.
- Signed still warns until reputation accumulates ("several weeks and hundreds of clean installs"). "EV certificates no longer bypass SmartScreen" (since 2024). No manual submission mechanism.
- Smart App Control blocks unsigned files without reputation (off on target).
- Costs: Microsoft Store MSIX free; Azure Artifact Signing ~$9.99/month, individuals USA and Canada only (not available to an individual in the Czech Republic); OV $150–300/year, key on HSM/token since June 2023; EV $400+/yr; self-signed = unsigned; SignPath Foundation free for qualifying open-source projects.
- Certum: Open Source Code Signing from €25 (code) / €49 (SimplySign cloud) / €69 (card set); Standard from €139 / €169 / €209; max 459 days validity from 2026-02-27. [not re-checked]

**Existing Wolfie conventions** [L, memory 93 days old]
- Source: `%USERPROFILE%\.claude\projects\C--Users-<user>-Desktop-Claude-code\memory\wolfie-app.md`.
- Python + Flask + pywebview, `py -m PyInstaller --noconfirm --clean PDF-to-Markdown.spec`, ~116 MB onefile exe, deployed to `%USERPROFILE%\Apps\PDF-to-Markdown\`, `py app.py --web` / `--server-only`, Flask on port 5000 with fallback, single-file `index.html` with CZ/EN i18n.
- pywebview latest 6.2.1 (https://pypi.org/pypi/pywebview/json). `%USERPROFILE%\Desktop\OCR project` is currently empty.

---

## 8 Lessons from wrapper projects

**GhostCorpTech/infinite-ai-text-recognizer** (https://github.com/GhostCorpTech/infinite-ai-text-recognizer) [C]
- Windows-only Tauri 2 (Rust + React/TS), MIT, v0.1.0, created 2026-08-23T17:41:17Z, pushed 2026-08-23T19:20:32Z, 2 commits, 0 stars/forks/issues. Unproven in the wild.
- MSI `Infinite.AI.Text.Recognizer_0.1.0_x64_en-US.msi` 5,251,072 B (notes say "3 MB"; https://api.github.com/repos/GhostCorpTech/infinite-ai-text-recognizer/releases). "On first launch it downloads about 10 GB and needs ~16 GB of free disk space — pick a drive other than C:."
- Verified only: CPU path, install from nothing, hardware detection, device patch, DOCX export, queue logic, installer bundling. Not verified: GPU profiles, NF4.
- Cargo deps: tauri 2, tauri-plugin-{opener,dialog,single-instance} 2, sysinfo 0.33, reqwest 0.12 (rustls, stream), tokio 1, zip 2, serde, uuid, chrono, parking_lot. Identifier `com.ghostcorptech.infiniteaitextrecognizer`, window 1100x760. Files: `src-tauri/src/{probe,paths,download,setup,engine,queue,export,i18n}.rs`, `python/{worker.py,device_patch.py}`, `src/components/{SetupWizard,Workspace}.tsx`.
- Layout (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/paths.rs): pointer file `%APPDATA%\InfiniteAITextRecognizer\location.txt`. Under root: `tools/` (uv.exe), `runtime/`, `venv/`, `model/` (weights + 5 remote-code .py), `worker/worker.py`, `outputs/`, `logs/`, `queue.json`. `install.json` (InstallRecord{root, profile, torch_index, completed, completed_at}) written only after all stages succeed.
- `SYSTEM_DRIVE_RESERVE_BYTES = 20 * 1024 * 1024 * 1024`. Bypasses the HF hub cache.
- Stages (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/setup.rs): Tools → Python → Torch → Deps → Model → Patch → SelfTest → Done. uv from `https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip`; `uv python install 3.12`; pins as section 2 (+ `bitsandbytes>=0.45` for Economy). Comment: transformers==4.57.1 "exact pin required".
- Download (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/download.rs): `HF_HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]` ("falling through to the mirror is the normal path"); `baidu/Unlimited-OCR/resolve/main/{filename}` (not pinned); `Range: bytes={already}-`; append only on 206; 416 with already>0 = complete; progress every 250 ms. Verification is size only. Weakness: a corrupt full-length file passes. [FC] From the Czech Republic its mirror fallback 308-redirects to huggingface.co, so it adds nothing.
- GPU probe (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/probe.rs lines 146–160, 208–233): nvidia-smi query; absence = no GPU.
- Bug: `pick_torch_index` returns the cu129 index for drivers ≥575, but cu129 has no Windows wheel for torch 2.10.0. It would fail on an RTX 4080 SUPER with a current driver. Unit tests assert cu129.
- Conflict: another angle (reading setup.rs) says the index is chosen from `cu126|cu128|cu130|cpu`, downgrading to cu126 for cards PyTorch dropped. The probe.rs line quotes are more specific. Either way, do not copy its index picker unverified. [unresolved]
- `device_patch.py` (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/python/device_patch.py): rewrites `torch.autocast("cuda", dtype=torch.bfloat16)` → `torch.autocast(_UNOCR_AUTOCAST, dtype=_UNOCR_DTYPE)`, `.to(torch.bfloat16)` → `.to(_UNOCR_DTYPE)`, `.cuda()` → `.to(_UNOCR_DEVICE)`, `.to("cuda")` / `device="cuda"` → `_UNOCR_DEVICE`, `max_length=max_length` → `max_new_tokens=max_length`, across three files. Driven by env `UNOCR_DEVICE` / `UNOCR_DTYPE`. Idempotent via sentinel `# --- infinite-ai-text-recognizer: model patch v2 applied ---`, keeps `.orig` backups, refuses to run if zero CUDA bindings are found. [FC] It rewrites the Apache-2.0 `modeling_deepseekv2.py`, so Apache section 4 applies to any app copying this approach.
- Worker (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/python/worker.py): CLI `--model-dir --device (cpu) --dtype (bfloat16) --quantize --selftest --lang`. Load `AutoModel.from_pretrained(str(model_dir), trust_remote_code=True, use_safetensors=True, dtype=torch_dtype)`. NF4: `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', double_quant)`, `device_map={'': 0}`.
- CPU keeps bf16 weights. `cpu_needs_fp32()` times bf16 vs fp32 matmul; if bf16 is >1.3x slower, `install_fp32_matmul_shims` wraps `torch.nn.functional.linear` and `torch.matmul`. No `torch.set_num_threads`. [FC] Per README the working CPU configuration runs vision encoders in fp32 (+0.8 GB) and decoder matmuls widened to fp32; naive bf16 took 114 s for the vision encoder on an i5-8400 instead of 10 s.
- Self-test: 900x1200 white page with PIL text ("Infinite AI Text Recognizer", "Self test 12345", "The quick brown fox"), page-shaped so gundam tiles it. Fails on empty output; reports seconds/device/dtype.
- Engine protocol (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/engine.rs): long-lived child process, `CREATE_NO_WINDOW`, env `UNOCR_DEVICE, UNOCR_DTYPE, HF_HOME, PYTHONIOENCODING=utf-8, PYTHONUNBUFFERED=1`. JSON-lines over stdin/stdout (request `{cmd,id,path,mode,max_new_tokens}`; responses Ready/Loaded/Progress/Result/Error/Log/Exited). Shutdown: send, wait 5 s, kill. "no ports, no server".
- Params: gundam or base, 35/128; multi-page 1024, 35/1024; default max_new_tokens 8192; `PDF_RENDER_DPI = 144`; `infer_multi` on the whole page list with no chunking.
- Missing: OOM handling, cancellation, `CUDA_VISIBLE_DEVICES`.
- Queue and export (https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/queue.rs, https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src-tauri/src/export.rs, https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/src/components/SetupWizard.tsx): `queue.json` written after every change with plain `fs::write` (not rename-atomic). States Pending/Running/Done/Failed/Cancelled; "Running" reset to Pending on restart. Export strips tags, converts `<PAGE>` to paragraph breaks, hand-builds DOCX as a zip. Wizard: probing → review → installing → failed → done. UI English + Russian.

**unlocr (whit3rabbit)** (https://github.com/whit3rabbit/unlocr, https://raw.githubusercontent.com/whit3rabbit/unlocr/main/src/tools/mod.rs) [C]
- Rust + Tauri GUI + CLI, MIT, 8 stars, releases v0.1.0–v0.3.2 (2026-07-04..07-10), last push 2026-07-18. Windows `unlocr_0.3.2_x64-setup.exe` 2,705,127 B (2.7 MB) / `.msi` 3.5 MB (https://api.github.com/repos/whit3rabbit/unlocr/releases/tags/v0.3.2). `cargo install unlocr` / brew.
- First run downloads into `%LOCALAPPDATA%\unlocr`: own patched llama-server from PR #24975 (`llama-rswa-20260704-win-x64.zip` 6.1 MB, SHA256-pinned, https://github.com/whit3rabbit/unlocr/releases/download/llama-rswa-20260704/llama-rswa-20260704-win-x64.zip), poppler (`oschwartz10612/poppler-windows v26.02.0-0`), pandoc 3.10, GGUFs from sahilchachra.
- sha256 checked against a pinned digest table ("Verified live against HF's file-metadata API"); Range resume; error "integrity check failed for {name}". Conflict: one angle said the downloader is undocumented in the README; the source-level description is better sourced.
- Server: `-m <gguf> --mmproj <mmproj> --host 127.0.0.1 --port N [--image-max-tokens N] [--chat-template deepseek-ocr]` (server/local.rs lines 288–320). Temperature 0, repeat_penalty 1.3, DRY (dry_allowed_length 4; "anti-loop / dense page" toggle → 2; dry_penalty_last_n -1). Default max_tokens 4096 per page. 144 DPI via pdftoppm. Pages POSTed one by one.
- Quality tiers `--quality best|good|less` = BF16 (~8 GB RAM) / Q8_0 (~6 GB, default) / Q4_K_M (~4 GB). Prompt presets: markdown, grounding, free, figure. `unlocr doctor` checks deps, integrity, RAM, disk. Settings → Dependencies dialog can redownload.
- Windows build is CPU-only: "Windows GPU users should compile from source" or pass `--llama-bin`. Issue #4 (2026-08-17, https://github.com/whit3rabbit/unlocr/issues/4) has no reply. `--gpu` = vLLM ("16 GB+ VRAM", `pip install -U vllm --pre`); `--endpoint URL` for remote.
- No existing wrapper delivers GPU-accelerated R-SWA GGUF inference on Windows.
- Known limitations: loops on blank/ruled pages, orphaned llama-server on Ctrl-C, unauthenticated 127.0.0.1 server, port races.

**franken_ocr (Dicklesworthstone)** (https://github.com/Dicklesworthstone/franken_ocr, https://raw.githubusercontent.com/Dicklesworthstone/franken_ocr/main/README.md) [C]
- Pure Rust, CPU-only by design. CLI `focr` + library crate (crates.io 0.9.0, 2026-08-23, 68 downloads; https://crates.io/api/v1/crates/franken_ocr, https://docs.rs/crate/franken_ocr/latest). 331 stars, 39 forks, 784 commits, last push 2026-09-22. Nightly Rust; `cargo install` "does not work".
- Licence conflict: README says MIT ("Copyright (c) 2026 Jeffrey Emanuel"); GitHub API says NOASSERTION; crates.io "Non-standard". One angle simply recorded "MIT". Read the LICENSE file before depending on it. [U]
- Version conflict: two angles cite v0.8.0 as the Windows release; the wrappers angle shows v0.9.0 (2026-08-23) current and Windows exe since v0.7.1 (2026-07-11). Releases: v0.9.0, v0.8.0 2026-08-20, v0.7.2 2026-07-13, v0.7.1, v0.7.0 2026-07-11, v0.6.0 2026-07-08. v0.9.0 exe size confirmed by fact-check.
- Use from another app: CLI only, no HTTP API. `focr-x86_64-pc-windows-msvc.exe` with `.sha256` sidecar. Installer `irm https://raw.githubusercontent.com/Dicklesworthstone/franken_ocr/main/install.ps1 | iex` → `%LOCALAPPDATA%\Programs\focr`. Commands: `focr pull`, `focr ocr page.png`, `--json`, `--robot` (NDJSON), `focr ocr-batch`, `focr ocr book.pdf --pages 3,5-9`, `--multi-page`.
- Resident warm-model daemon: loopback TCP, token auth, 10 idle minutes (`FOCR_RESIDENT_IDLE_SECS`; opt out `--no-resident` / `FOCR_NO_RESIDENT=1`).
- Library API: `OcrEngine::new()?; engine.recognize(Path::new("page.png"))?`, `recognize_dynamic`, `recognize_batch`.
- PDFs: only scanned/image PDFs (JPEG/DCTDecode, CCITT G4, Flate/LZW). Born-digital vector/text pages, JPXDecode and JBIG2 are rejected. Applies `/Rotate` metadata.
- Flags: `--base-size, --image-size, --crop-mode gundam|base, --max-length, --temperature, --no-repeat-ngram, --ngram-window, --split-spreads, --extract-figures`. Env: `FOCR_MODEL_PATH, FOCR_MODEL_DIR, FOCR_THREADS, FOCR_TIMING=1, FOCR_STAGE_BUDGET_FORWARD_MS` (default 600000; 0 = unlimited), `FOCR_NO_REPEAT_NGRAM` (35), `FOCR_FORCE_ARCH avx2|avxvnni|avx512vnni`.
- Weights `.focrq`: decoder GEMMs int8 per output channel; vision tower, projector, embeddings, router, norms kept high precision. `unlimited-ocr.v0.7.0.int8.focrq` in 3 parts (1,957,046,720 + 1,957,046,720 + 243,355,343); recipe `unlimited-ocr-ffn-int8-attn-bf16-lmhead-bf16-v1`; cached in `~/.cache/franken_ocr/models/`; hashes verified against an embedded manifest (https://api.github.com/repos/Dicklesworthstone/franken_ocr/releases/tags/v0.7.0).
- HF mirror https://huggingface.co/Dicklesworthstone/franken_ocr-weights/tree/main (also got-ocr2.int8.focrq 814 MB, wasm-int4 3 GB). GGUF explicitly not supported (https://api.github.com/repos/Dicklesworthstone/franken_ocr/issues/3/comments). `focr convert model.safetensors -o unlimited-ocr.focrq --quant int8`.
- Quality: historical real-page CER 0.0094; v0.7.0 corpus CER 0.193 with hard page 0.616; int4 WASM CER 0.0856.
- RAM: 8 GB "a realistic floor"; inference peaks well above 4 GB.
- Issues: #17 open (2026-09-26/27, https://api.github.com/repos/Dicklesworthstone/franken_ocr/issues/17, https://github.com/Dicklesworthstone/franken_ocr/issues/17): 0.9.0 `--multi-page` on x86_64 AVX2 returns only `<PAGE>` (7 bytes, exit 0); stateless fallback exceeds the 600 s budget. #15 tall screenshots ~0.5% yield with exit 0 (fixed 0.9.0, low-yield guard <50 chars/megapixel → exit code 8). #12 install.sh resolved latest to a weights tag. #16 timeout could not be disabled. #7 Windows pull failures. #6 CUDA "deferred roadmap item with no timeline". #1 "7GB memory usage, no recognition" on a 105x35 px image. #4 indexed-colour PDF rejected.

**say4n/unlimited-ocr-container** (https://raw.githubusercontent.com/say4n/unlimited-ocr-container/main/Dockerfile) [C]
- Docker only, Linux. `:cpu` (python:3.12-slim, torch 2.10.0 from /whl/cpu, fp32) and `:gpu` (nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04 + SGLang wheel + kernels==0.11.7).
- Clones baidu/Unlimited-OCR at `c7ade8c686d8f026c2db43b58320e0a1e39e4064`. `HF_HOME=/models/huggingface`, `TRANSFORMERS_CACHE=/models/huggingface`, `-v "$PWD/models:/models"`, optional HF_TOKEN.
- 19 stars, 4 forks, last push 2026-06-24, MIT. Files: Dockerfile 2,509 B, scripts/cpu_infer.py 7,377 B, scripts/entrypoint.sh 203 B.
- CPU flags `--image_file/--image_dir/--pdf, --output_dir, --image_mode gundam|base, --pdf_dpi 300`.
- Issues: #2 (drag-and-drop UI request), PR #1 (`libnuma1` needed, verified on RTX 3060 with SGLang in Docker on Linux), #3 "error from registry: denied".
- Useful idea: monkeypatching `.cuda` instead of patching files.

**Docling** [C]
- Issue #3679 closed completed 2026-08-10 (https://github.com/docling-project/docling/issues/3679). PR #3944 merged 2026-08-10 (v2.119.0). PR #4037 "use official Unlimited-OCR prompt" merged 2026-08-24 (v2.122.0, 2026-08-25). Releases: https://api.github.com/repos/docling-project/docling/releases.
- Preset (https://raw.githubusercontent.com/docling-project/docling/main/docling/datamodel/stage_model_specs.py lines 1772–1797): `preset_id 'unlimited_ocr'`, `VlmEngineType.API_OPENAI`, prompt `'<image>document parsing.'`, `response_format UNLIMITED_OCR_MARKDOWN`, max_new_tokens 8192, scale 2.0, api params `{'model': 'unlimited-ocr', 'max_tokens': 8192, 'skip_special_tokens': False}`.
- Catalog: Transformers no, MLX no, API yes, vLLM yes. API-only, so not a local Windows engine.
- Reusable: `normalize_unlimited_ocr_annotations()`, `parse_unlimited_ocr_markdown()`. Open #3943 (MLX).

**Other Windows precedents**
- [FC] **pdf2epub PR #41** (https://github.com/overcuriousity/pdf2epub/pull/41): native Windows, RTX 4060 8 GB, transformers bf16: good output, no looping, ~62 s/page, 7.05 GiB peak. The only clean native-Windows GPU success report found (self-reported). Same card is ~4x faster on Fedora 44. [C as reported]
- Wasihub1/unlimited_ocr_cuda (https://github.com/Wasihub1/unlimited_ocr_cuda) [L]: run.bat installs Python 3.12, creates `env`. `requirements-cuda.txt` uses the cu129 extra index and `torch==2.10.0+cu129`, which contradicts the index evidence that no such Windows wheel exists (URL returns 403). It admits "Real GPU inference and 16 GB compatibility are not validated by the mocked tests". Command `./run.bat --device cuda --setup-only`.
- GMfatcat/Unlimited-OCR-Local (demo #70): WSL2 because "SGLang does not support native Windows".
- [FC] Native Windows evidence, revised: issue #58 ran on Windows 11 + RTX 3080 Ti (with quality problems), the note.com test ran on Windows + GTX 1060 3GB (sm_61, CPU path), and pdf2epub reports a clean success on Windows + RTX 4060. The earlier statement "no clean success report exists" is withdrawn. No report exists for a 16 GB card on native Windows.
- PR #49 "Add macOS (MPS / CPU) and WSL support" closed/abandoned; defaulted CPU dtype to float32 "for safety". #48 macOS request. Windows issue search: https://github.com/baidu/Unlimited-OCR/issues?q=windows.

**Distilled lessons**
1. Tiny installer, engine and weights fetched once into a user-visible folder with a ready marker written last.
2. Long-lived worker process, not per-document invocation. Load takes ~10 s or more and several GB.
3. Verify by sha256 once after download. Do not hash at boot.
4. Pin everything: HF revision, transformers 4.57.1, torch 2.10.0, llama.cpp build if used.
5. Patch must fail loudly if upstream code changes and must cover `forward()`.
6. Always run a self-test on a page-shaped synthetic image; treat empty output as failure; record s/page.
7. Treat empty text with exit code 0 as failure. It happens in GGUF, franken_ocr and transformers paths.
8. Per-page processing with app-side concatenation is the conservative default. Multi-page is the fragile path in every wrapper, and on transformers its VRAM grows quadratically.
9. Tag stripping belongs in an export or post-processing layer. Keep raw output. Never let upstream `save_results` code `eval()` model output.
10. Do not trust wrapper GPU code. None of the wrappers reviewed here has verified GPU inference on Windows; the one native-Windows GPU data point (pdf2epub) is a plain transformers script.
11. [FC] Check free VRAM before loading, not total VRAM.

---

## 9 Known failure modes

| # | Failure | Evidence | Mitigation |
|---|---|---|---|
| 1 | Repetition loops | Issue #55 (open, https://github.com/baidu/Unlimited-OCR/issues/55): 1,651-page OmniDocBench set; 0.24% of pages in gundam, 1.2% in base; 8,000–80,000+ chars; 100–738 s (700+ s) per looping page. The 35-gram guard misses shorter units ("typically 6-15 characters = 8-20 tokens"). | Always pass 35/128 (or 35/1024). Wall-clock and token cap per page. Two-pass: detect loops by zlib compression ratio <0.05 on >5,000 chars, retry only those pages. |
| 2 | Tighter n-gram settings hurt | Global ngram_size=5 collapses OmniDocBench overall 91.97 → 64.56. Applying (5,256) only to looping pages still raised text EditDist 0.0868 → 0.0885 because 5-grams ban legitimate tags and bbox coordinates; doubled output on one newspaper page. | Do not use a small n-gram globally. Test `repetition_penalty=1.1` or a 3-gram second processor. [U which is best] |
| 3 | Loops on specific content | #24 (hang on table image, endless `<\|det\|>table [0,0,999,999]`; PR #29; closed). #84 (vLLM 0.25.1, 300 DPI): two-column patent text "50 or greater, 70 or greater, ..." 2,608 repeats, 51,815 chars, finish_reason "length"; ST.25 sequence listings become huge HTML tables (https://github.com/baidu/Unlimited-OCR/issues/84). #82 llama.cpp CPU infinite repeat (https://github.com/baidu/Unlimited-OCR/issues/82). Blank/ruled pages (unlocr). | Blank-page pre-check. llama.cpp: `--repeat-last-n 512` (default 64 too small), stop sequences, `--temp 0`, 300 DPI, DRY; "some garbled text persisted". |
| 4 | Hallucination | HF discussion #3 (https://huggingface.co/baidu/Unlimited-OCR/discussions/3): "when it can't read the pixels, it invents". Ranking on a hard low-res legal form: olmOCR-2 > Qianfan-OCR > PaddleOCR-VL > HunyuanOCR > Unlimited-OCR; "Fastest of the five, but the least accurate". HF discussion #4 (https://huggingface.co/baidu/Unlimited-OCR/discussions/4): "LEAST faithful". Issue #58 (https://github.com/baidu/Unlimited-OCR/issues/58): 3,000 Chinese images gave many empty outputs plus irrelevant looping 2017 corporate/banking text on blank images. | Ink-coverage or variance check before inference. Never treat output as verified for medical or legal use. Optional cross-check engine (PaddleOCR-VL, Tesseract-ces). |
| 5 | Empty output | #99: sparse synthetic page → empty text, exit code 0. #90: full-page scans empty across gundam/base/1280 (non-official prompt, transformers 4.55.0, torch 2.13). #32: one gundam page empty in 0.6 s while base succeeded. vLLM: empty usually = missing `<image>` prefix or wrong skip_special_tokens. Claim that it needs the exact recipe comes from a now-404 repo. [L] | Validate non-empty; retry in the other mode; use the official prompt. |
| 6 | Rotated text | #79 (https://github.com/baidu/Unlimited-OCR/issues/79): lines rotated 15°, -20°, 45°, 90° → 45° and 90° missing, numbers corrupted (#88015→#88009, #87980→#87890), fabricated line "Rotated 98deg#88009 due 2026-09-30". Whole-page 90°/180° handling [U]. | Auto-orient pages before inference. |
| 7 | Multi-page collapse | #53 (https://github.com/baidu/Unlimited-OCR/issues/53): 8 Chinese legal pages, correct for pages 1–2 then garbage from page 3 (~4K–6K generated tokens), on MacBook M5 with non-standard settings (image_size=640, max 16384, ngram 15, window 512). Attribution conflict: one angle calls it MPS-only, two say CPU float32 also degrades (after ~12 min). Reproduction on CUDA with official settings [U]. Paper: edit distance doubles at 40+ pages. | Chunk 10–20 pages or go per page; sanity-check each chunk. |
| 8 | Silent truncation | `max_length` is total budget; generate stops. | Compute budget per chunk; detect a missing final `<PAGE>` count. |
| 9 | Small text lost in base mode | Paper error analysis; tall images "squashed". | Gundam for single pages; split tall images into strips. |
| 10 | Tables, reading order, structure | Tables on scanned PDFs degrade (#16). Stylistic ruled lines misread (#62). Reading-order edit 0.045 (v1.5) / 0.129 (v1.6). No cross-page paragraph merge (#47, https://github.com/baidu/Unlimited-OCR/issues/47). Headings without `#` (#68). | App-side post-processing. |
| 11 | Handwriting, non-Latin scripts, non-zh/en languages | Section 5; maintainer: "mainly support English and Chinese". | Second engine if needed. |
| 12 | CUDA hard-coding | Section 2. | Patched code. |
| 13 | stdout None in windowed build | [FC] Downgraded: `print()` is a no-op when `sys.stdout` is None; transformers replaces a None stderr. Not a crash source. | eval_mode=True; optional custom streamer for progress. |
| 14 | n-gram guard possibly not firing | PR #57 claim; v4.57.1 source reading (twice) disagrees. [L, not executed] | Assert in self-test. |
| 15 | Download corruption or stall | Section 6. | sha256 + fallback ladder (ModelScope as the independent source). |
| 16 | OOM on long PDFs | PR #86 (open, https://github.com/baidu/Unlimited-OCR/pull/86) adds `--pages-per-batch`, default one page per batch. [FC] Cause identified from code: eager attention allocates ~60 × L² bytes during prefill (20 pages ~1.8 GB, 40 pages ~7.2 GB). pdf2epub: 8 GB card OOM without `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. | ≤20–25 base pages per chunk; check free VRAM; set `expandable_segments:True`; delete temp images. |
| 17 | vLLM-specific | #76 "Total number of attention heads (10) must be divisible by tensor parallel size (4)"; #63 gundam crashes vLLM EngineCore. | Not relevant to the transformers path. |
| 18 | Apple-only | masked_scatter_ broadcast bug on MPS (#18, https://github.com/baidu/Unlimited-OCR/issues/18); MPS crashes mid-generation (#81). | Not relevant on Windows; the expand_as fix is safe to keep. |
| 19 | GGUF-specific | Aggressive DRY garbles HTML tables; Q4 quality cliff; mainline MHA ~2x CER vs R-SWA (0.7792% vs 0.3344%); #98/#99 Arc/Vulkan. | Q5_K_M or higher; mild DRY. |
| 20 | [FC] `eval()` on model output | `infer()` with save_results=True evals generated text containing `line_type`; `extract_coordinates_and_label` evals box strings in `infer()` and `infer_multi()`. | eval_mode=True; `infer_multi(save_results=False)`; own parser with `ast.literal_eval` or regex. |
| 21 | [FC] VRAM already occupied | Target had 10,961 MiB in use by a game at probe time. | Check free VRAM; refuse or fall back to a quantized/CPU path. |
| 22 | [FC] Slow on Windows vs Linux | pdf2epub: same RTX 4060 is ~4x slower on Windows (62 s vs ~13.9 s/page). Cause unknown. | Benchmark; keep peak VRAM well below the card's limit to avoid shared-memory spill. [U] |
| 23 | [FC] bf16 on x86 CPU | 9–20x slower than fp32 outside Sapphire Rapids+; sabafallah reports MoE routing drift in bf16 (MPS). | fp32 on CPU. |

**Inconsistency in the findings on row 1:** one angle reports "14 of 1,651 pages (1.2%)". 14/1,651 is 0.85%, while 1.2% would be about 20 pages and 0.24% about 4. The percentages are probably right and "14" may be a different subset. Not addressed by any fact-check. Check issue #55 before quoting a count. [U]

Issue search used for CPU/Windows: https://github.com/baidu/Unlimited-OCR/issues?q=is%3Aissue+windows+OR+cpu+OR+cuda+OR+flash (open issues ≈ #53–#99 visible; closed issues not exhaustively reviewed).

---

## 10 Open questions answerable only by local testing

**Accuracy**
1. Czech accuracy. Test set dense in ř ů ě č š ž ď ť ň á é í ó ú ý (invoices, letters, book page, including scans and photos, which MORE does not cover) at 150/200/300 dpi, scored by character error rate on diacritics, in gundam and base. Run the parent `deepseek-ai/DeepSeek-OCR` on the same images. Zero-install first check: https://huggingface.co/spaces/baidu/Unlimited-OCR.
2. Tokenizer round-trip of "Příliš žluťoučký kůň úpěl ďábelské ódy". [FC: encodability confirmed from tokenizer.json; the round-trip itself is a formality]
3. Handwritten Czech, if it matters.
4. Does the 35-gram guard corrupt legitimately repetitive Czech content (tables of identical rows, repeated headers)?
5. Gundam vs base default for single pages, given the issue #66 dispute.
6. Do DeepSeek-style prompts work, and do they help on Czech? [FC: one data point, `Free OCR.` read Latin text on a crop but full pages came back empty]

**Speed and memory**
7. Seconds per page and peak VRAM on the RTX 4080 SUPER, transformers eager bf16, gundam vs base.
8. Peak VRAM for a 20–40-page `infer_multi` chunk. [FC: predicted ~8.5 GB at 20 pages, ~14 GiB at 40 pages; confirm]
9. x86 CPU speed and RAM on the Core Ultra 7 265K: fp32 vs bf16 with fp32 shims. [FC: naive bf16 expected 9–20x slower; is bf16 numerically fine (MoE routing drift)?]
10. Model load time and PyInstaller/torch cold-start time on Windows.

**Behaviour**
11. Does `infer(eval_mode=True)` output still contain `<|ref|>`/`<|det|>` tags?
12. Tables HTML or pipe-markdown; formulas LaTeX? [FC: HTML strongly indicated by `<td>`/`<tr>` tokens]
13. Does `SlidingWindowNoRepeatNgramProcessor` actually fire under transformers 4.57.1? [FC: source says yes; still not executed]
14. Does the issue #53 collapse reproduce on CUDA with official settings?
15. Best loop mitigation and per-page wall-clock cap.
16. Blank-page threshold and runaway detection thresholds (e.g. zlib ratio <0.05 on >5,000 chars).
17. Whole-page 90°/180° rotation handling.
18. Exact gundam separator-token counts.

**Stack**
19. Does the whole chain work natively on Windows 11 + Python 3.11 + torch 2.10.0+cu128 (or cu130) + transformers 4.57.1? [FC: one self-reported success on Windows + RTX 4060; versions of that run not verified]
20. cu128 vs cu130 on driver 617.14: any behavioural or speed difference?
21. Does AutoModel ever dereference the stale nested `language_config.auto_map`?
22. ~~Offline loading of trust_remote_code from a local dir on 4.57.1; folder naming~~ [FC: RESOLVED by source: PR #37716 is in 4.57.1; folder is `transformers_modules/<sanitized basename>/`, no hash subfolder. A runtime test is still worthwhile.]
23. ~~Does `from_pretrained` on 4.57.1 accept `disable_mmap`?~~ [FC: RESOLVED: no.] Still open: what is the non-mmap path for error 1455?
24. Does trust_remote_code import work inside a PyInstaller onedir build with writable `HF_MODULES_CACHE`? Which `--collect-all` / `copy_metadata` entries are needed?
25. Compatibility with newer torch (2.13/2.14). [FC: PARTLY RESOLVED: issue #90 ran torch 2.13 + transformers 4.55.0 on an L4; 2.14 and Windows untested]

**Download**
26. hf_xet on this PC: stalls or not? Should Xet be off by default on Windows? [FC: all cited stall issues are now closed]
27. ~~`list_repo_tree` / `lfs.sha256` field names on hub 0.36.x~~ [FC: RESOLVED: `f.lfs.sha256` works]
28. ~~Partial-file location in local_dir mode on 0.36.x~~ [FC: RESOLVED: `<local_dir>/.cache/huggingface/download/<short_hash>.<etag>.incomplete`]
29. ~~Does the pinned hf_xet write a chunk cache?~~ [FC: RESOLVED for hf_xet 1.6.0: disabled by default]
30. ~~ModelScope Range support~~ [FC: RESOLVED: 206 on the weights file; resume from a large offset untested.] ~~Is hf-mirror.com needed from the Czech Republic?~~ [FC: RESOLVED: it only redirects to huggingface.co]

**Fallback engine**
31. Does stock llama.cpp (b11221, CUDA 13.4 or CPU build) run the GGUF correctly on Windows? Does llama-server's multimodal path work on a current build? [FC: MHA vs R-SWA quality has one measurement, CER 0.7792% vs 0.3344%; reproduce on Czech pages]
32. x86 Windows speed of franken_ocr int8, and its real licence.
33. Do bitsandbytes NF4/int8 or AWQ load with the custom MoE code on Windows?

**Added by fact-check**
34. Is the ~4x Windows-vs-Linux slowdown present on a 16 GB card? Is it WDDM shared-memory spill?
35. How much free VRAM does the target have in normal use, and what should the app do when a game holds ~11 GB?
36. Does `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` help on Windows?
37. Does the vLLM Windows community fork (SystemPanic/vllm-windows) run this model?
38. Is VC++ redistributable 14.50.35719 actually needed for torch 2.10.0 on a clean Windows 11?

**Decisions for the user, not tests**
- Audience, and therefore whether code signing matters.
- Engine strategy: (A) torch + transformers, (B) llama.cpp + GGUF, or (C) both.
- Is one-shot multi-page a must-have, or is per-page enough?
- Install location (`%LOCALAPPDATA%` vs user-chosen drive).
- Whether the engine venv may be uv-managed 3.12 while the launcher is 3.11.
- Version-bump policy for the pinned commit, and whether to host a split fallback copy of the weights.
- Support for Pascal/Maxwell cards and <8 GB VRAM machines.
- PDF DPI default (300 vs 200 vs 144).
- Whether the engine should be pluggable. If Czech fails, best-evidenced alternatives on MORE Czech text are dots.ocr (99.16), HunyuanOCR (97.96) and PaddleOCR-VL (94.73; explicit Czech listing).
- [FC] Licence handling: ship a third-party notices file with MIT + Apache-2.0 texts.

---

## 11 Fact-check log

Five independent fact-checks: FC1 Python API and dependencies (not refuted; 7 errors, 8 missing details), FC2 hardware and speed (refuted in part), FC3 licence and gating (refuted in part), FC4 language support (refuted in part), FC5 packaging and download (refuted in part). Raw copies of FC2's sources are in `%USERPROFILE%\AppData\Local\Temp\fc`.

**A. Corrections applied (claim was wrong)**

| # | Section | Was | Now | Source |
|---|---|---|---|---|
| 1 | 1 | 19 siblings | 20 siblings | FC1, HF API |
| 2 | 1 | "MIT for code and weights" | repo-level MIT; code is mixed MIT + Apache-2.0 (DeepSeek-AI/HuggingFace, Meta, FastChat material); Apache section 4 duties when patching | FC3 |
| 3 | 1, 5 | maintainers never replied to #3, #25 | both answered by MurphyYin (Baidu intern, first author): "mainly support English and Chinese" | FC4 |
| 4 | 1 | needed payload ≈6.69 GB | 6,683,168,104 B = 6.68 GB; skippable 95,201,548 B | FC5 |
| 5 | 2 | load/infer snippet "README, verbatim" | not verbatim; "Does NOT support crop mode" is from the docstring | FC1 |
| 6 | 2 | infer.py "SGLang HTTP client only" | it launches `sglang.launch_server` via Popen (lines 97, 121), then acts as client | FC1 |
| 7 | 2, 9 | `sys.stdout` None breaks `infer_multi` in windowed builds | `print()` is a no-op; not a crash source | FC1 |
| 8 | 2 | `attn_implementation='sdpa'` → KeyError | ValueError; `flash_attention_2` → ImportError, or KeyError only if flash_attn is installed | FC1 |
| 9 | 2 | `check_imports` raises for einops/easydict/addict/matplotlib | true for Hub loads only; local dir checks `modeling_unlimitedocr.py` only, einops/easydict → ModuleNotFoundError | FC1 |
| 10 | 2 | sabafallah requires transformers "4.57.1+" | `transformers==4.57.1` | FC1 |
| 11 | 2 | app-adapted load uses bf16 on CPU | fp32 on CPU | FC1, FC2 |
| 12 | 3 | "largest job should stay under ~10 GB" | wrong for transformers: eager attention adds ~60 × L² bytes; 40 pages ≈ 14 GiB; 32K prefill ≈ 64 GB | FC2 |
| 13 | 3 | "12.6 GB fp32 / 6.3 GB bf16" from PR #57, as VRAM | from PR #49, peak system RAM | FC2 |
| 14 | 3 | 273 s vs 3.6 s from the dev.to article, hardware not given | from a Medium benchmark (RTX 4070 Laptop 8 GB); dev.to has no timings; stays [U] | FC2 |
| 15 | 3, 8 | RTX 4060 row "~7 GB, ~60 s", [L]; "no clean native-Windows success report" | native Windows, 62 s/page, 7.05 GiB, good output; Fedora ~13.9 s/page; vLLM FP8 ~1.3 s/page; statement withdrawn | FC2 |
| 16 | 3, 7 | mmproj "774.27 MiB (0.769 GB)", "0.77 GB" | two files: 811,876,448 B (0.81 GB) and 825,245,568 B (0.83 GB) | FC2 |
| 17 | 3 | issue #81 row "CPU bf16"; i5-8400 row "CPU bf16" | dtype not stated in #81; i5-8400 ran fp32 vision encoders + fp32-widened matmuls | FC2 |
| 18 | 3 | reported working GPUs as one list | split by runtime; VRAM sizes for #58/#79 are inferences | FC2 |
| 19 | 3 | GMfatcat [L] secondary; M5 MacBook [L] without URL; LumiVerseHR "RTX 4090"; paper TPS "(SGLang)" | GMfatcat self-reported; M5 source found, [C]; 4090 only in the repo description; engine not named in the paper | FC2 |
| 20 | 3, 7 | MHA vs R-SWA quality "unmeasured" | measured once: CER 0.7792% vs 0.3344% | FC2 |
| 21 | 3 | AWQ ≈2–3 GB; aimadetools CPU figure as transformers | 2.82 GB, 1,284,913 downloads; CPU figure is GGUF/llama.cpp | FC2 |
| 22 | 5 | INSIDE zh/en claim [L], "primary text not located" | [C], primary text is the #3 comment | FC4 |
| 23 | 5 | "512 placeholder tokens at ids 128000+" | 830 added tokens: 800 placeholders 128000–128799 + specials 128800–128826 | FC4 |
| 24 | 5 | PaddleOCR-VL beats DeepSeekOCR on pl, de, sk | also on hu (99.37 vs 99.26) | FC4 |
| 25 | 5 | MORE "printed documents only"; values "not cross-checked" | no such statement in MORE; values re-parsed and match; text-only table and thin-sample caveats added | FC4 |
| 26 | 5 | Vietnamese failure "consistent with" forgetting | parent already weak on Vietnamese (62.86); weaker evidence | FC4 |
| 27 | 5 | tokenizer claim [L], tokenizer.json not read | [C], tokenizer.json read; Czech letters have single tokens | FC4 |
| 28 | 5 | HF discussion #22 ~2026-09-12; PaddleOCR-VL-1.6 lists Czech | created 2026-09-13; language list is from the generic 0.9B doc, 1.6 card lists only en/zh/multilingual | FC4 |
| 29 | 6 | hf-mirror.com "full mirror" in the fallback ladder | 308-redirects to huggingface.co from CZ; moved last; ModelScope is the independent fallback | FC3, FC5 |
| 30 | 6 | ModelScope "byte-identical" | identical weights and model files; `.gitattributes` differs, extra `configuration.json` | FC3, FC5 |
| 31 | 6 | `HF_HUB_DISABLE_SYMLINKS` available on 0.36.x, "=1 forces" | does not exist on 0.36.x; silent no-op | FC5 |
| 32 | 6 | partial file `<blob>.<uuid8>.incomplete` | main-branch only; 0.36.x uses `blob_path + ".incomplete"` / `<short_hash>.<etag>.incomplete` | FC5 |
| 33 | 6 | dotted/relative path → ModuleNotFoundError [C] | outdated for 4.57.1 (`_sanitize_module_name`) | FC5 |
| 34 | 6 | xet-core #446 "Windows/ReFS deadlock" | title does not mention ReFS; all cited stall issues are closed | FC5 |
| 35 | 7 | torch ranges cu126/cpu 2.10.0–2.13.0, cu128 2.10.0/2.11.0 | cu126 2.6.0–2.14.0, cpu to 2.14.0, cu128 2.7.0–2.11.0 | FC5 |
| 36 | 7 | llama.cpp `-hf` → `LLAMA_CACHE` or `%LOCALAPPDATA%\llama.cpp` | follows the HF cache chain since commit 8c7957ca | FC5 |
| 37 | 7 | cu126 "ends with PyTorch 2.15" | 2.14 is the last release with cu126 | FC5 |
| 38 | 7 | PyTorch 2.10 "CUDA 13.0 is now the stable default" | conflicts with PyPI metadata (2.10 default is CUDA 12.8); quote likely belongs to 2.11 | FC5 |
| 39 | 7 | VC++ 14.50.35719 "fixes" WinError 1114 | not established; issue still open | FC5 |
| 40 | 7 | code-signing facts cited to the smartscreen-reputation page | cost facts are on the code-signing-options page | FC5 |
| 41 | 7 | rokm: "the torch library in the app is about 4GB" | the asker's sentence; rokm said 2.6 GB onefile and "cannot be split" | FC5 |
| 42 | 7 | uv 17 MB | 17,955,780 B = 18.0 MB | FC5 |
| 43 | 5 | inside.com.tw URL with trailing period | trailing period removed | FC4 evidence URL |

**B. Additions from fact-checks (missing, now included)**
- `generate()` exists only through AutoModel's GenerationMixin injection (FC1).
- `torch_dtype` deprecated in 4.57.1; tokenizers 0.23.0 final never released (FC1).
- `eval()` on model output in the save_results paths, security risk (FC1).
- Gundam tiles fixed at 640 px; images ≤640 px get no tiles; eval_mode returns None without `<image>` (FC1).
- README inconsistency kernels 0.9.0 vs 0.11.7; vLLM Windows community fork (FC1).
- Remote-code files byte-identical between initial commit d549bb9d and main (FC1).
- Target CPU Core Ultra 7 265K; 10,961 MiB VRAM in use at probe time (FC2).
- New speed rows: DGX Spark, PR #57 M4 Pro, A770 wall time on Fedora, Q8_0/Q6_K tok/s, franken_ocr second page; PR #49 load-time caveat; ~400 MB/page encoder figure; `expandable_segments:True` (FC2).
- MIT grant over weights rests on LICENSE and card tag only; parent DeepSeek-OCR MIT and ungated (FC3).
- Anonymous HEAD/Range verification on HF; ModelScope Range 206 (FC3, FC5).
- MORE text-only scores, sample size, page-count discrepancy 1,288 vs 1,237; kushdab claim; Italian request; `angle_mode` parameter; OmniDocBench language-value inconsistency; issue #45 second user (FC4).
- hub 0.36.2 date 2026-02-06; `dry_run` absent; `lfs.sha256` confirmed; hf_xet chunk cache disabled; `disable_mmap` absent in 4.57.1; PR #37716 included; local-dir module folder naming and basename collision; free-space floor thin; exact byte counts for wheels, Python builds, cudart, unlocr setup; GitHub Releases 1000 assets; b11222 published (FC5).

**C. Drift only (values re-measured, not errors)**
- HF likes 4,304 → 4,306. GitHub stars 26,407–26,409 → 26,427; forks 2,757–2,758 → 2,760. ModelScope downloads 136,436 → 136,471.

**D. Confirmed as stated (no change)**
- Dependency pins, Windows wheel availability, cu129 gap, transformers 4.x lock, signatures and line numbers, `.cuda()`/autocast/bf16 counts, flash-attn guard, n-gram processor reading, config and file hashes, commit history, paper figures, Table 4, KV-cache arithmetic, all GGUF byte sizes and CER figures, NVFP4, bitsandbytes requirements, local probe values, HF gating flags, LICENSE hash, CC BY 4.0, GitHub Releases 2 GiB limit, ChengCui quote, Vietnamese/Bengali/Arabic/Hebrew/Devanagari reports, arXiv 2601.03714 quote, DeepSeek-OCR training data, all wheel/DLL sizes, llama.cpp PR states, driver floors, uv `--torch-backend`, PyInstaller hooks, xet-core PR #967, hub 0.36.2 fast path and size-only checks.

**E. Remaining unconfirmed or unresolved**
- No speed or VRAM measurement on an RTX 4080 SUPER; no native-Windows report on a 16 GB card.
- Quadratic prefill memory figures are computed from code, not executed.
- Cause and applicability of the 4x Windows slowdown.
- Medium benchmark body (403); its snippets contradict each other.
- "14 of 1,651 pages" count in issue #55.
- Issue #53 attribution (MPS-only vs CPU too) and CUDA reproduction.
- GhostCorp torch index picker: probe.rs vs setup.rs reading conflict.
- franken_ocr licence (MIT vs NOASSERTION vs "Non-standard") and x86 speed.
- CPU bf16 correctness (sabafallah routing drift vs issue #81 success).
- Whether the n-gram processor fires at runtime; whether eval_mode output keeps tags; LaTeX formulas.
- Nested `language_config.auto_map` effect.
- "No maintainer reply" on sampled issues other than #3/#25: the method that missed those two replies was used for the rest.
- MIT over weights is an inference from repo-level licence; no explicit statement on commercial use.
- ModelScope resume from a large offset; ModelScope SDK integrity behaviour.
- PaddleOCR-VL-1.6 Czech support (inherited, not stated on the card).
- PyInstaller + trust_remote_code by direct test; `uv venv --relocatable`; Nuitka size; Ollama import R-SWA; GGUF multi-page; SGLang on Windows; vLLM Windows fork.
- Attribution of the "CUDA 13.0 is now the stable default" quote.

**F. Explicitly not re-checked by any fact-check**
- FC1: note.com dtype error report, say4n monkeypatch details, SGLang docs CUDA 13 statement, Docling issue #4030 quote, exact contents of PR #56.
- FC5: Certum prices, Nuitka size claim, ComfyUI/Pinokio/LM Studio precedents, PyApp options, ONNX repo sizes, Ollama community import, the "split archive" skill page, PyInstaller issues #7646/#5672/#2956, CPython #102169.
- Sections 4 (benchmarks, output format), 8 (wrapper internals beyond sizes and README quotes) and 9 were not the subject of a dedicated fact-check; only items touched by FC1–FC5 were re-verified.

**G. Fact-check evidence URLs not cited elsewhere in the sheet**
- https://download.pytorch.org/whl/cu126/torch/ and https://download.pytorch.org/whl/cu130/torch/ (cited in section 2), https://github.com/baidu/Unlimited-OCR/pull/86 (section 9)
- https://github.com/huggingface/transformers/pull/46836 (section 1), https://github.com/docling-project/docling/issues/3679 (section 8)
- https://raw.githubusercontent.com/GhostCorpTech/infinite-ai-text-recognizer/main/README.md (section 3)
- https://api.github.com/repos/baidu/Unlimited-OCR/issues/3/comments, https://api.github.com/repos/baidu/Unlimited-OCR/issues/25/comments (section 5)
- https://raw.githubusercontent.com/huggingface/xet-core/v1.6.0/xet_runtime/src/config/groups/chunk_cache.rs (section 6)
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/common.cpp (section 7)
- https://learn.microsoft.com/en-us/azure/artifact-signing/faq (section 7)

All fact-check evidence URLs are therefore present in sections 1–10; this list only points to where the less obvious ones were placed.