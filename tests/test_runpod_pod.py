"""`scripts/runpod_pod.py`nin saf parçaları - ağsız.

Betiğin iki işi var ve ikisi de burada sabitlenir:

1. Her oturumda değişen port eşlemesini `local/.env.bulut`'a yazmak. Dosya
   parolaları da taşıyor; güncelleme onlara ve yorumlara DOKUNMAMALI.
2. Pod'u tek bir spesifikasyondan oluşturmak. Spesifikasyon RunPod'daki
   kurulumun tek kaynağı; ölçülmüş kısıtlar (yalnız Secure Cloud'da ağ diski,
   CUDA >= 12.8, HTTP vekili yok) burada kilitlenir.

Parola ve API anahtarı hiçbir çıktıda görünmemeli - `masked` ve `scrub`.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "runpod_pod.py"


def _load():
    name = "runpod_pod_script"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rp = _load()

_TEMPLATE = (
    "# MAHİR - BULUT KİPİ AYARLARI (şablon)\n"
    "# Pod'un TCP ucu.\n"
    "MAHIR_RAG_URL=http://<pod-ip>:<rag-portu>/agents\n"
    "MAHIR_OCR_URL=http://<pod-ip>:<ocr-portu>\n"
    "\n"
    "# Üretmek için:  python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
    "MAHIR_RAG_SHARED_SECRET=gizli-rag\n"
    "MAHIR_OCR_SHARED_SECRET=gizli-ocr\n"
)

_POD = {
    "id": "abc123",
    "desiredStatus": "RUNNING",
    "publicIp": "203.0.113.7",
    "portMappings": {"22": 40022, "8001": 40001, "8002": 40002},
    "env": {"MAHIR_RAG_SHARED_SECRET": "gizli-rag"},
}


class ApiKeyParsingTests(unittest.TestCase):
    def test_accepts_the_runpodctl_spellings(self):
        for text in ('apikey = "abc123"', "apiKey='abc123'", "api_key=abc123", '  APIKEY = "abc123"  # yorum'):
            with self.subTest(text=text):
                self.assertEqual(rp.parse_api_key(text), "abc123")

    def test_finds_the_key_among_other_lines(self):
        self.assertEqual(rp.parse_api_key('# not\napiurl = "https://x"\napikey = "k-1"\n'), "k-1")

    def test_missing_key_is_empty(self):
        self.assertEqual(rp.parse_api_key("# yalniz yorum\n"), "")


class EnvFileUpdateTests(unittest.TestCase):
    """Port eşlemesi her oturumda değişiyor; güncelleme yalnız iki URL satırını değiştirmeli."""

    URLS = {"MAHIR_RAG_URL": "http://203.0.113.7:40001/agents", "MAHIR_OCR_URL": "http://203.0.113.7:40002"}

    def test_only_the_url_lines_change(self):
        updated = rp.set_env_values(_TEMPLATE, self.URLS)
        before, after = _TEMPLATE.splitlines(), updated.splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        self.assertEqual([a for _b, a in changed], [f"{k}={v}" for k, v in self.URLS.items()])

    def test_secrets_and_comments_survive(self):
        values = rp.read_env_values(rp.set_env_values(_TEMPLATE, self.URLS))
        self.assertEqual(values["MAHIR_RAG_SHARED_SECRET"], "gizli-rag")
        self.assertEqual(values["MAHIR_OCR_SHARED_SECRET"], "gizli-ocr")
        self.assertIn("# MAHİR - BULUT KİPİ AYARLARI (şablon)", rp.set_env_values(_TEMPLATE, self.URLS))

    def test_crlf_files_stay_crlf(self):
        # Dosyayı PowerShell/Notepad CRLF ile kaydetmiş olabilir.
        updated = rp.set_env_values(_TEMPLATE.replace("\n", "\r\n"), self.URLS)
        self.assertNotIn("\n", updated.replace("\r\n", ""))

    def test_missing_keys_are_appended(self):
        updated = rp.set_env_values("# bos\n", self.URLS)
        self.assertEqual(rp.read_env_values(updated), self.URLS)

    def test_a_commented_key_is_not_mistaken_for_the_setting(self):
        updated = rp.set_env_values("#MAHIR_RAG_URL=eski\n", {"MAHIR_RAG_URL": "yeni"})
        self.assertIn("#MAHIR_RAG_URL=eski", updated)
        self.assertEqual(rp.read_env_values(updated)["MAHIR_RAG_URL"], "yeni")


class SecretFillingTests(unittest.TestCase):
    def test_fills_only_empty_secrets(self):
        text = _TEMPLATE.replace("gizli-ocr", "")
        filled_text, filled = rp.fill_missing_secrets(text, lambda: "uretilen")
        self.assertEqual(filled, ["MAHIR_OCR_SHARED_SECRET"])
        values = rp.read_env_values(filled_text)
        self.assertEqual(values["MAHIR_RAG_SHARED_SECRET"], "gizli-rag")  # dolu olana dokunulmadı
        self.assertEqual(values["MAHIR_OCR_SHARED_SECRET"], "uretilen")

    def test_existing_secrets_are_never_regenerated(self):
        text, filled = rp.fill_missing_secrets(_TEMPLATE, lambda: "uretilen")
        self.assertEqual(filled, [])
        self.assertEqual(text, _TEMPLATE)


class PodAddressTests(unittest.TestCase):
    def test_urls_come_from_the_mapped_ports(self):
        self.assertEqual(
            rp.service_urls(_POD),
            {"MAHIR_RAG_URL": "http://203.0.113.7:40001/agents", "MAHIR_OCR_URL": "http://203.0.113.7:40002"},
        )

    def test_integer_keys_are_accepted_too(self):
        pod = {**_POD, "portMappings": {22: 40022, 8001: 40001, 8002: 40002}}
        self.assertEqual(rp.service_urls(pod)["MAHIR_OCR_URL"], "http://203.0.113.7:40002")

    def test_initializing_pod_is_not_ready(self):
        # Belge: IP pod başlarken boş gelir.
        for pod in ({**_POD, "publicIp": ""}, {**_POD, "portMappings": {"8001": 40001}}):
            with self.subTest(pod=pod):
                with self.assertRaises(rp.PodNotReady):
                    rp.service_urls(pod)

    def test_ssh_target(self):
        self.assertEqual(rp.ssh_target(_POD), ("203.0.113.7", 40022))


class PodSpecTests(unittest.TestCase):
    ENV = {
        "MAHIR_RAG_SHARED_SECRET": "gizli-rag",
        "MAHIR_OCR_SHARED_SECRET": "gizli-ocr",
        "SSH_PUBLIC_KEY": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIexample kullanici@makine",
        "MAHIR_AUTOSTART": "1",
    }

    def _body(self):
        return rp.build_pod_body(
            name="mahir-gpu",
            image="ghcr.io/peykan1071/mahir-gpu:abc",
            data_center="EU-RO-1",
            gpu_ids=["NVIDIA RTX A5000", "NVIDIA RTX A4500"],
            volume_id="vol-1",
            env=self.ENV,
        )

    def test_network_volume_requires_secure_cloud(self):
        # "Network volumes are only available for Pods in the Secure Cloud."
        body = self._body()
        self.assertEqual(body["cloudType"], "SECURE")
        self.assertEqual(body["networkVolumeId"], "vol-1")
        self.assertEqual(body["volumeMountPath"], "/workspace")
        self.assertEqual(body["volumeInGb"], 0)

    def test_only_tcp_ports_no_http_proxy(self):
        # HTTP vekili 100 sn'de kesiyor; analiz turu daha uzun sürebiliyor.
        self.assertEqual(sorted(self._body()["ports"]), ["22/tcp", "8001/tcp", "8002/tcp"])

    def test_driver_must_support_the_images_cuda(self):
        versions = self._body()["allowedCudaVersions"]
        self.assertIn("12.8", versions)
        self.assertTrue(all(tuple(map(int, v.split("."))) >= (12, 8) for v in versions))

    def test_gpu_priority_and_data_center_are_kept(self):
        body = self._body()
        self.assertEqual(body["gpuTypeIds"], ["NVIDIA RTX A5000", "NVIDIA RTX A4500"])
        self.assertEqual(body["dataCenterIds"], ["EU-RO-1"])

    def test_env_carries_secrets_key_and_autostart(self):
        self.assertEqual(self._body()["env"], self.ENV)

    def test_masked_copy_hides_secrets_and_leaves_the_original(self):
        body = self._body()
        shown = json.dumps(rp.masked(body), ensure_ascii=False)
        self.assertNotIn("gizli-rag", shown)
        self.assertNotIn("gizli-ocr", shown)
        self.assertNotIn(self.ENV["SSH_PUBLIC_KEY"], shown)
        self.assertEqual(body["env"]["MAHIR_RAG_SHARED_SECRET"], "gizli-rag")


class ScrubTests(unittest.TestCase):
    def test_error_messages_never_carry_secrets(self):
        text = rp.scrub("HTTP 400: env MAHIR_RAG_SHARED_SECRET=gizli-rag gecersiz", ["gizli-rag", ""])
        self.assertNotIn("gizli-rag", text)
        self.assertIn("***", text)


if __name__ == "__main__":
    unittest.main()
