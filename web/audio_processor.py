"""Audio processing: STT + TTS with local OmniVoice / Volcengine support."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
import torch
import websocket
from faster_whisper import WhisperModel

try:
    from gradio_client import Client
except ImportError:  # local OmniVoice is optional when Volcengine is used
    Client = None


GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"

# ── Local OmniVoice ───────────────────────────────────────────────────────────
OMNI_VOICE_LIST = ["jok老师", "叶奈法"]
OMNI_DEFAULT_VOICE = OMNI_VOICE_LIST[0]

# ── Volcengine TTS V3 / 豆包语音合成模型 2.0 ────────────────────────────────
VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

VOLCENGINE_VOICE_LIST = [
    # Uranus series / 豆包语音合成 2.0
    "zh_female_vv_uranus_bigtts",           # Vivi 2.0
    "zh_female_xiaohe_uranus_bigtts",       # 小何 2.0
    "zh_male_m191_uranus_bigtts",           # 云舟 2.0
    "zh_male_taocheng_uranus_bigtts",       # 小天 2.0
    # Mars series / 豆包语音合成 1.0
    "zh_male_baqiqingshu_mars_bigtts",      # Edward 霸道总裁
    "zh_female_wenroushunv_mars_bigtts",    # Emma 温柔淑女
    "zh_female_shaoergushi_mars_bigtts",    # Tina 少儿故事
    "zh_male_silang_mars_bigtts",           # William 四郎
    "zh_male_jieshuonansheng_mars_bigtts",  # James 解说男声
    "zh_female_jitangmeimei_mars_bigtts",   # Grace 鸡汤妹妹
    "zh_female_tiexinnvsheng_mars_bigtts",  # Sophia 贴心女生
    "zh_female_qiaopinvsheng_mars_bigtts",  # Mia 俏皮女生
    "zh_female_mengyatou_mars_bigtts",      # Ava 萌丫头
    "zh_female_cancan_mars_bigtts",         # Luna 灿灿
    "zh_female_qingxinnvsheng_mars_bigtts", # Olivia 清新女生
    "zh_female_linjia_mars_bigtts",         # Lily 邻家
    # Moon series
    "zh_female_wanwanxiaohe_moon_bigtts",   # Isabella 台湾腔
    "zh_male_guozhoudege_moon_bigtts",      # Andrew 粤语
    "zh_female_gaolengyujie_moon_bigtts",   # Charlotte 高冷御姐
    "zh_male_jingqiangkanye_moon_bigtts",   # Thomas 北京腔
    "zh_male_wennuanahu_moon_bigtts",       # Mark 温暖大叔
    "zh_female_linjianvhai_moon_bigtts",    # Lila 邻家女孩
    "zh_male_shaonianzixin_moon_bigtts",    # Ethan 少年自信
    "zh_male_yuanboxiaoshu_moon_bigtts",    # Joseph 远播小数
    "zh_female_daimengchuanmei_moon_bigtts",# Elena 呆萌川妹
    "zh_male_yangguangqingnian_moon_bigtts",# George 阳光青年
    "zh_female_shuangkuaisisi_moon_bigtts", # Aria 爽快飒姐
    # Jupiter series
    "zh_female_vv_jupiter_bigtts",          # vv 活泼灵动女声
    "zh_female_xiaohe_jupiter_bigtts",      # xiaohe 甜美台妹
    "zh_male_yunzhou_jupiter_bigtts",       # yunzhou 清爽男声
    "zh_male_xiaotian_jupiter_bigtts",      # xiaotian 磁性男声
    # Saturn series
    "zh_female_xueayi_saturn_bigtts",       # 儿童绘本
]

AUDIO_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "ogg_opus": "audio/ogg",
    "wav": "audio/wav",
    "pcm": "application/octet-stream",
    "aac": "audio/aac",
    "flac": "audio/flac",
}


def get_voice_list(tts_provider: str = "local") -> list[str]:
    """Return available voice names based on current TTS provider."""
    if tts_provider == "volcengine":
        return VOLCENGINE_VOICE_LIST
    return OMNI_VOICE_LIST


def get_default_voice(tts_provider: str = "local") -> str:
    """Return the default voice for the given provider."""
    if tts_provider == "volcengine":
        return "zh_female_vv_uranus_bigtts"
    return OMNI_DEFAULT_VOICE


class AudioProcessor:
    def __init__(self, voice_config: dict | None = None):
        self.stt_model = None
        self.omni_client = None
        self._voice_config = voice_config or {}

    def _get_tts_provider(self) -> str:
        return self._voice_config.get("tts_provider", "local")

    def _get_stt_provider(self) -> str:
        return self._voice_config.get("stt_provider", "local")

    def _get_volcengine_cfg(self) -> dict:
        return self._voice_config.get("volcengine", {})

    def _get_omni_client(self):
        """Lazy-load OmniVoice so Volcengine users do not need localhost:7862."""
        if self.omni_client is None:
            if Client is None:
                raise RuntimeError("未安装 gradio_client，请执行 pip install gradio_client")
            self.omni_client = Client("http://localhost:7862/")
        return self.omni_client

    # ── STT ───────────────────────────────────────────────────────────────────
    def _load_stt(self):
        if self.stt_model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute = "float16" if device == "cuda" else "int8"
            print(f"[Audio] Loading STT model (tiny, {device})...")
            self.stt_model = WhisperModel("tiny", device=device, compute_type=compute)
            print("[Audio] STT model loaded.")
        return self.stt_model

    def transcribe(self, audio_bytes: bytes) -> dict:
        """STT: dispatch to provider based on config."""
        if self._get_stt_provider() == "volcengine":
            return self._transcribe_volcengine(audio_bytes)
        return self._transcribe_local(audio_bytes)

    def _transcribe_local(self, audio_bytes: bytes) -> dict:
        """STT via local faster-whisper."""
        model = self._load_stt()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name

        try:
            segments, info = model.transcribe(tmp, language="zh")
            text = "".join(seg.text for seg in segments)
            return {
                "text": text.strip(),
                "duration_ms": int(info.duration * 1000),
            }
        finally:
            Path(tmp).unlink(missing_ok=True)

    @staticmethod
    def _convert_to_pcm(audio_bytes: bytes) -> bytes:
        """Convert audio bytes to PCM 16kHz 16-bit mono via ffmpeg."""
        proc = subprocess.Popen(
            [
                "ffmpeg",
                "-i", "-",
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-loglevel", "error",
                "-",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pcm_data, stderr = proc.communicate(input=audio_bytes)

        if proc.returncode != 0:
            msg = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"音频转码失败: {msg}")
        if not pcm_data:
            raise RuntimeError("音频转码结果为空")
        return pcm_data

    def _transcribe_volcengine(self, audio_bytes: bytes) -> dict:
        """STT via Volcengine WebSocket ASR API."""
        cfg = self._get_volcengine_cfg()
        app_id = cfg.get("app_id", "")
        access_token = cfg.get("access_token", "")
        api_key = cfg.get("api_key", "")

        use_api_key = bool(api_key)
        use_old_auth = bool(app_id) and bool(access_token)
        if not use_api_key and not use_old_auth:
            return {"text": "", "duration_ms": 0, "error": "火山引擎未配置新版控制台 API Key"}

        try:
            pcm_data = self._convert_to_pcm(audio_bytes)
        except RuntimeError as e:
            return {"text": "", "duration_ms": 0, "error": str(e)}

        ws_url = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        headers = {"X-Api-Resource-Id": cfg.get("asr_resource_id", "volc.bigasr.sauc.duration")}
        if use_api_key:
            headers["X-Api-Key"] = api_key
        else:
            headers["X-Api-App-Key"] = app_id
            headers["X-Api-Access-Key"] = access_token

        try:
            ws = websocket.create_connection(
                ws_url,
                header=[f"{k}: {v}" for k, v in headers.items()],
                timeout=60,
            )
        except Exception as e:
            return {"text": "", "duration_ms": 0, "error": f"WebSocket 连接失败: {e}"}

        proto_ver = 0b0001
        hdr_size = 0b0001
        ser_json = 0b0001
        comp_gzip = 0b0001
        msg_full_req = 0b0001
        msg_audio = 0b0010
        flag_pos_seq = 0b0001
        flag_neg_seq = 0b0011

        def _header(msg_type: int, flags: int) -> bytes:
            return struct.pack(
                "!BBBB",
                (proto_ver << 4) | hdr_size,
                (msg_type << 4) | flags,
                (ser_json << 4) | comp_gzip,
                0x00,
            )

        result_text = ""
        try:
            seq = 1
            req_config = {
                "app": {
                    "appid": app_id,
                    "token": access_token,
                    "cluster": "volcengine_asr",
                },
                "audio": {
                    "format": "pcm",
                    "rate": 16000,
                    "channel": 1,
                    "bits": 16,
                    "codec": "raw",
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": True,
                    "enable_punc": True,
                    "enable_ddc": True,
                    "show_utterances": False,
                    "result_type": "single",
                },
            }
            payload = gzip.compress(json.dumps(req_config).encode("utf-8"))
            ws.send_binary(_header(msg_full_req, flag_pos_seq) + struct.pack("!i", seq) + struct.pack("!I", len(payload)) + payload)
            seq += 1

            chunk_size = 16000 * 2 * 200 // 1000
            for offset in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[offset:offset + chunk_size]
                is_last = offset + chunk_size >= len(pcm_data)
                flags = flag_neg_seq if is_last else flag_pos_seq
                send_seq = -seq if is_last else seq
                compressed = gzip.compress(chunk)
                frame = _header(msg_audio, flags) + struct.pack("!i", send_seq) + struct.pack("!I", len(compressed)) + compressed
                ws.send_binary(frame)
                seq += 1

            while True:
                raw = ws.recv()
                if not isinstance(raw, bytes) or len(raw) < 8:
                    continue

                msg_type = (raw[1] >> 4) & 0x0F
                flags = raw[1] & 0x0F
                compression = raw[2] & 0x0F
                hdr_sz = (raw[0] & 0x0F) * 4
                pos = hdr_sz
                if flags & 0b0001:
                    pos += 4
                pld_sz = struct.unpack("!I", raw[pos:pos + 4])[0]
                pos += 4
                pld = raw[pos:pos + pld_sz]
                if compression == comp_gzip:
                    pld = gzip.decompress(pld)
                body = json.loads(pld.decode("utf-8"))

                if msg_type == 0b1001:
                    text = body.get("result", {}).get("text", "")
                    if text:
                        result_text += text
                    if body.get("result", {}).get("is_final", False):
                        break
                elif msg_type == 0b1111:
                    err = body.get("message", "未知错误")
                    return {"text": "", "duration_ms": 0, "error": f"火山引擎 ASR 错误: {err}"}

            return {"text": result_text.strip(), "duration_ms": 0}

        except websocket.WebSocketTimeoutException:
            return {"text": result_text.strip(), "duration_ms": 0, "error": "火山引擎 ASR 超时"}
        except websocket.WebSocketConnectionClosedException:
            return {"text": result_text.strip(), "duration_ms": 0}
        except Exception as e:
            return {"text": result_text.strip(), "duration_ms": 0, "error": f"火山引擎 ASR 请求失败: {e}"}
        finally:
            try:
                ws.close()
            except Exception:
                pass

    # ── TTS ───────────────────────────────────────────────────────────────────
    def synthesize(self, text: str, speed: float = 1.0, voice: str | None = None) -> tuple[bytes, str]:
        """TTS: dispatch to provider based on config. Returns (audio_bytes, mime_type)."""
        if self._get_tts_provider() == "volcengine":
            return self._synthesize_volcengine(text, speed, voice)
        return self._synthesize_omni(text, speed, voice)

    def _synthesize_omni(self, text: str, speed: float = 1.0, voice: str | None = None) -> tuple[bytes, str]:
        """TTS via local OmniVoice: text -> wav bytes."""
        voice_name = voice or OMNI_DEFAULT_VOICE
        h = hashlib.md5((text + str(speed) + voice_name).encode()).hexdigest()[:12]
        cache_path = GENERATED_DIR / f"tts_{h}.wav"
        if cache_path.exists():
            return cache_path.read_bytes(), "audio/wav"

        print(f"[TTS] Calling OmniVoice (voice={voice_name})...")
        wav_path, _ = self._get_omni_client().predict(
            voice_name,
            text,
            "",
            None,
            speed,
            "",
            "Auto",
            False,
            api_name="/do_job",
        )
        wav_bytes = Path(wav_path).read_bytes()
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(wav_bytes)
        print(f"[TTS] OK ({len(wav_bytes)} bytes, voice={voice_name})")
        return wav_bytes, "audio/wav"

    @staticmethod
    def _speed_to_speech_rate(speed: float) -> int:
        """Map UI speed 0.5~2.0 to Doubao speech_rate -50~100."""
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 1.0
        speed = max(0.5, min(2.0, speed))
        return max(-50, min(100, int(round((speed - 1.0) * 100))))

    @staticmethod
    def _extract_audio_b64(obj: Any) -> str | None:
        """Find base64 audio payload in common Doubao V3 response shapes."""
        if not isinstance(obj, dict):
            return None

        candidates = [
            obj.get("data"),
            obj.get("audio"),
            obj.get("audio_data"),
            obj.get("payload"),
            obj.get("result", {}).get("data") if isinstance(obj.get("result"), dict) else None,
            obj.get("result", {}).get("audio") if isinstance(obj.get("result"), dict) else None,
            obj.get("result", {}).get("audio_data") if isinstance(obj.get("result"), dict) else None,
        ]
        for item in candidates:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                for key in ("data", "audio", "audio_data"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return None

    @staticmethod
    def _decode_base64_audio(value: str) -> bytes:
        """Decode a base64 payload, accepting data:audio/...;base64, prefixes."""
        if "," in value and value.lstrip().lower().startswith("data:"):
            value = value.split(",", 1)[1]
        return base64.b64decode(value)

    @staticmethod
    def _looks_like_audio(data: bytes) -> bool:
        return data.startswith((b"ID3", b"OggS", b"RIFF", b"fLaC")) or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")

    @staticmethod
    def _iter_json_objects_from_text(buffer: str):
        """Yield JSON objects from newline/SSE/raw-concatenated JSON text."""
        decoder = json.JSONDecoder()
        idx = 0
        length = len(buffer)
        while idx < length:
            while idx < length and buffer[idx].isspace():
                idx += 1
            if idx >= length:
                break

            if buffer.startswith("data:", idx):
                line_end = buffer.find("\n", idx)
                if line_end == -1:
                    break
                line = buffer[idx + 5:line_end].strip()
                idx = line_end + 1
                if not line or line == "[DONE]":
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
                continue

            try:
                obj, end = decoder.raw_decode(buffer, idx)
            except json.JSONDecodeError:
                line_end = buffer.find("\n", idx)
                if line_end == -1:
                    break
                line = buffer[idx:line_end].strip()
                idx = line_end + 1
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
            else:
                yield obj
                idx = end

    def _handle_volcengine_tts_event(self, obj: Any, audio_chunks: list[bytes]) -> bool:
        """
        Handle one Doubao V3 TTS event.
        Returns True when the stream is explicitly finished.
        """
        if not isinstance(obj, dict):
            return False

        code = obj.get("code")
        message = obj.get("message") or obj.get("msg") or ""
        audio_b64 = self._extract_audio_b64(obj)

        if audio_b64:
            try:
                audio_chunks.append(self._decode_base64_audio(audio_b64))
            except Exception as e:
                raise RuntimeError(f"火山引擎返回了无法解码的音频 base64: {e}") from e

        if code in (20000000, "20000000"):
            return True

        if code in (None, 0, "0"):
            return False

        raise RuntimeError(f"火山引擎 TTS V3 错误: code={code}, message={message}")


    @staticmethod
    def _infer_tts_resource_id_from_speaker(speaker: str) -> str:
        """Infer Doubao TTS resource_id from speaker naming convention."""
        speaker = (speaker or "").strip()
        if speaker.startswith(("S_", "ICL_")):
            return "seed-icl-1.0"
        if "_uranus_" in speaker:
            return "seed-tts-2.0"
        if any(f"_{series}_" in speaker for series in ("mars", "moon", "jupiter", "saturn")):
            return "seed-tts-1.0"
        return "seed-tts-2.0"

    def _resolve_tts_resource_id(self, configured_resource_id: str | None, speaker: str) -> str:
        """Resolve and validate resource_id so speaker/model mismatch fails locally with a clear message."""
        configured = (configured_resource_id or "auto").strip()
        inferred = self._infer_tts_resource_id_from_speaker(speaker)
        if configured.lower() in {"", "auto"}:
            return inferred

        # 豆包语音合成 2.0 音色目前是 uranus 系列；mars/moon/jupiter/saturn 等不要配 seed-tts-2.0。
        if configured == "seed-tts-2.0" and "_uranus_" not in speaker:
            raise RuntimeError(
                "火山引擎 TTS 配置不匹配：resource_id=seed-tts-2.0 只能配豆包 2.0 音色。"
                f"当前 voice_type={speaker} 不是 uranus 系列。"
                "请把 voice_type 改成 zh_female_vv_uranus_bigtts，或把 resource_id 改成 auto/seed-tts-1.0。"
            )
        if configured == "seed-tts-1.0" and "_uranus_" in speaker:
            raise RuntimeError(
                "火山引擎 TTS 配置不匹配：uranus 系列是豆包 2.0 音色，"
                "请把 resource_id 改成 auto 或 seed-tts-2.0。"
            )
        if configured == "seed-icl-1.0" and not speaker.startswith(("S_", "ICL_")):
            raise RuntimeError(
                "火山引擎 TTS 配置不匹配：seed-icl-1.0 通常用于声音复刻/ICL 音色，"
                "普通大模型音色请使用 auto、seed-tts-1.0 或 seed-tts-2.0。"
            )
        return configured

    def _synthesize_volcengine(self, text: str, speed: float = 1.0, voice: str | None = None) -> tuple[bytes, str]:
        """TTS via Volcengine V3 HTTP Chunked API."""
        cfg = self._get_volcengine_cfg()
        app_id = cfg.get("app_id", "")
        access_token = cfg.get("access_token", "")
        api_key = cfg.get("api_key", "")
        resource_id = cfg.get("resource_id", "auto")
        speaker = voice or cfg.get("voice_type", "zh_female_vv_uranus_bigtts")
        resource_id = self._resolve_tts_resource_id(resource_id, speaker)
        audio_format = cfg.get("audio_format", "mp3")
        sample_rate = int(cfg.get("sample_rate", 24000))

        use_api_key = bool(api_key)
        use_old_auth = bool(app_id) and bool(access_token) and not use_api_key
        if not use_api_key and not use_old_auth:
            raise RuntimeError("火山引擎未配置新版控制台 API Key")

        speech_rate = self._speed_to_speech_rate(speed)
        cache_ext = "ogg" if audio_format in {"opus", "ogg_opus"} else audio_format
        mime = AUDIO_MIME_TYPES.get(audio_format, "audio/mpeg")
        h = hashlib.md5(
            json.dumps(
                {
                    "provider": "volcengine-v3",
                    "text": text,
                    "speed": speed,
                    "speaker": speaker,
                    "resource_id": resource_id,
                    "format": audio_format,
                    "sample_rate": sample_rate,
                    "speech_rate": speech_rate,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:12]
        cache_path = GENERATED_DIR / f"tts_{h}.{cache_ext}"
        if cache_path.exists():
            return cache_path.read_bytes(), mime

        req_params: dict[str, Any] = {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
        }
        if speech_rate != 0:
            req_params["audio_params"]["speech_rate"] = speech_rate

        # If you need expressive/standard explicitly, add it to config.json:
        # "model": "seed-tts-2.0-standard" or "seed-tts-2.0-expressive".
        model_name = cfg.get("model", "")
        if model_name:
            req_params["model"] = model_name

        payload = {
            "user": {"uid": cfg.get("uid", "localchat")},
            "req_params": req_params,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        if use_api_key:
            headers["X-Api-Key"] = api_key
        else:
            headers["X-Api-App-Id"] = app_id
            headers["X-Api-Access-Key"] = access_token

        print(f"[TTS] Calling Volcengine V3 (speaker={speaker}, resource={resource_id})...")

        audio_chunks: list[bytes] = []
        text_buffer = ""
        finished = False

        try:
            timeout = httpx.Timeout(60.0, connect=10.0, read=60.0)
            with httpx.Client(timeout=timeout) as cli:
                with cli.stream("POST", VOLCENGINE_TTS_URL, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        detail = resp.read().decode("utf-8", errors="replace")[:1000]
                        raise RuntimeError(f"火山引擎 TTS V3 错误 (HTTP {resp.status_code}): {detail}")

                    content_type = resp.headers.get("content-type", "")
                    for raw_chunk in resp.iter_bytes():
                        if not raw_chunk:
                            continue

                        # Some gateways may return raw audio directly; keep this fallback.
                        if not text_buffer and not audio_chunks and "json" not in content_type and self._looks_like_audio(raw_chunk):
                            audio_chunks.append(raw_chunk)
                            for rest in resp.iter_bytes():
                                if rest:
                                    audio_chunks.append(rest)
                            finished = True
                            break

                        try:
                            text_buffer += raw_chunk.decode("utf-8")
                        except UnicodeDecodeError:
                            # Binary audio fallback.
                            audio_chunks.append(raw_chunk)
                            continue

                        consumed_any = False
                        for obj in self._iter_json_objects_from_text(text_buffer):
                            consumed_any = True
                            if self._handle_volcengine_tts_event(obj, audio_chunks):
                                finished = True
                        if consumed_any:
                            # V3 events are newline/JSON framed in normal cases. Clearing avoids
                            # re-processing already handled objects.
                            text_buffer = ""

            if text_buffer.strip() and not finished:
                for obj in self._iter_json_objects_from_text(text_buffer):
                    if self._handle_volcengine_tts_event(obj, audio_chunks):
                        finished = True

            if not audio_chunks:
                raise RuntimeError(
                    "火山引擎未返回音频数据，请检查音色、Resource ID、App ID/Access Key 是否正确，"
                    "以及该音色是否已在豆包语音控制台开通。"
                )

            audio_bytes = b"".join(audio_chunks)
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(audio_bytes)
            print(f"[TTS] OK ({len(audio_bytes)} bytes, speaker={speaker})")
            return audio_bytes, mime

        except httpx.RequestError as e:
            raise RuntimeError(f"火山引擎 TTS 请求失败: {e}") from e
