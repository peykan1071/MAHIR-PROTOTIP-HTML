"""MAHİR GPU imajı doğrulaması - Python kontrolleri (2-6).

`scripts/verify_gpu_image.sh` tarafından çağrılır; tek başına da koşar:

    python scripts/verify_gpu_image.py

Her kontrol bağımsız koşar: biri düşse de diğerleri çalışır ki tek koşuda
bütün tablo görünsün. Çıkış kodu, düşen kontrol sayısıdır.

Kontroller bu imajın ÖLÇÜLMÜŞ kırılma noktalarından türedi (bkz. Dockerfile):

* paddle ÖNCE, torch SONRA aynı süreçte import edilir - OCR işçisinin sırası.
* torch'un ve paddle'ın yüklediği cuDNN, torch'un KENDİ metadata'sında
  pinlediği sürüm olmalı. Sabit bir sayı (91002) değil, metadata'dan
  türetiliyor: imaj yükseltilince betik güncellenmeden doğru kalsın.
  Yakaladığı arıza: paddle kurulumunun cuDNN'i sessizce 9.5'e düşürmesi
  (ilk build'de ölçüldü; pip yalnız uyarı basıp 0 ile çıkıyordu).
  `paddle.device.get_cudnn_version()` derlendiği sürümü DEĞİL çalışma anında
  yüklenen kütüphaneyi bildiriyor (ölçüldü: metadata pini 9.5.1.17 iken
  91002 döndü) - yani 9.5'e derlenmiş paddle'ın 9.10 ile koştuğunun doğrudan
  ölçümü.
* Triton kernel'i bu DOSYADA tanımlı: `python -c` ile verilen kodda
  `inspect.getsourcelines` kaynağı bulamıyor ve `triton.jit` düşüyor
  (ölçüldü). PaddleOCR-VL'nin `transformers` motoru çalışma anında tam olarak
  bu derlemeyi yapıyor; önceki RunPod denemesinin en büyük blokeri buydu.
"""

from __future__ import annotations

import sys
from importlib.metadata import requires, version
from typing import Callable

CUDNN_PACKAGE = "nvidia-cudnn-cu12"


def cudnn_int(text: str) -> int:
    """`9.10.2.21` -> 91002 (cuDNN 9'un `version()` biçimi)."""
    major, minor, patch = (int(part) for part in text.split(".")[:3])
    return major * 10000 + minor * 100 + patch


def torch_cudnn_pin() -> str:
    """torch'un metadata'sındaki `nvidia-cudnn-cu12==X` pinini döndürür."""
    for requirement in requires("torch") or []:
        name, _, rest = requirement.partition("==")
        if name.strip() == CUDNN_PACKAGE and rest:
            return rest.split(";")[0].strip()
    raise RuntimeError(f"torch metadata'sında {CUDNN_PACKAGE} pini bulunamadı")


def check_imports() -> str:
    import paddle  # noqa: F401 - bilerek ÖNCE (OCR işçisiyle aynı sıra)
    import torch

    return f"paddle {paddle.__version__}, torch {torch.__version__}"


def check_torch_cuda() -> str:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "torch.cuda.is_available() False - GPU konteynere verilmemiş "
            "olabilir (docker run --gpus all)"
        )
    return torch.cuda.get_device_name(0)


def check_cudnn() -> str:
    import paddle
    import torch

    pin = torch_cudnn_pin()
    want = cudnn_int(pin)
    got_torch = torch.backends.cudnn.version()
    got_paddle = paddle.device.get_cudnn_version()
    detail = (
        f"torch pini {pin} ({want}), kurulu {version(CUDNN_PACKAGE)}, "
        f"torch yükledi {got_torch}, paddle yükledi {got_paddle}"
    )
    if got_torch != want or got_paddle != want:
        raise RuntimeError(detail)
    return detail


def check_paddle_gpu() -> str:
    import paddle

    # run_check() kendi başına ayrıntılı çıktı basar; ek olarak küçük bir GPU
    # işleminin SONUCU doğrulanır ki başarı yalnız bir mesaja dayanmasın.
    paddle.utils.run_check()
    values = (paddle.to_tensor([1.0, 2.0, 3.0], place=paddle.CUDAPlace(0)) * 2).numpy().tolist()
    if values != [2.0, 4.0, 6.0]:
        raise RuntimeError(f"GPU'da yanlış sonuç: {values}")
    return "run_check + GPU tensör işlemi doğru"


def check_triton() -> str:
    import torch
    import triton
    import triton.language as tl

    @triton.jit
    def double_kernel(x_ptr, y_ptr, n, BLOCK: tl.constexpr):
        offsets = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
        mask = offsets < n
        tl.store(y_ptr + offsets, tl.load(x_ptr + offsets, mask=mask) * 2.0, mask=mask)

    x = torch.arange(8, device="cuda", dtype=torch.float32)
    y = torch.empty_like(x)
    double_kernel[(1,)](x, y, 8, BLOCK=8)
    torch.cuda.synchronize()
    expected = [value * 2.0 for value in range(8)]
    if y.tolist() != expected:
        raise RuntimeError(f"yanlış sonuç: {y.tolist()}")
    return f"triton {triton.__version__}: kernel derlendi ve doğru sonuç verdi"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("2/6 import: önce paddle, sonra torch", check_imports),
    ("3/6 torch.cuda", check_torch_cuda),
    ("4/6 cuDNN: torch ve paddle, torch'un pinini yüklüyor", check_cudnn),
    ("5/6 paddle GPU", check_paddle_gpu),
    ("6/6 Triton çalışma anı derlemesi", check_triton),
]


def main() -> int:
    failures = 0
    for name, check in CHECKS:
        print(f"== {name}", flush=True)
        try:
            print(f"   TAMAM  {check()}", flush=True)
        except Exception as error:  # noqa: BLE001 - her arıza tabloya girsin
            failures += 1
            print(f"   DÜŞTÜ  {type(error).__name__}: {error}", flush=True)
    return failures


if __name__ == "__main__":
    sys.exit(main())
