"""Audio processing: STT + TTS with dual provider support (local OmniVoice / Volcengine)."""

import gzip
import hashlib
import io
import json
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx
import torch
import websocket
from faster_whisper import WhisperModel
from gradio_client import Client

GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"

# ── Local OmniVoice ───────────────────────────────────────────────────────────

OMNI_VOICE_LIST = ["jok老师", "叶奈法"]
OMNI_DEFAULT_VOICE = OMNI_VOICE_LIST[0]

# ── Volcengine TTS (V3 API — 豆包语音合成模型2.0) ─────────────────────────

VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

VOLCENGINE_VOICE_LIST = [
    # Mars series (2025-04 initial release)
    "zh_male_baqiqingshu_mars_bigtts",       # Edward 霸道总裁
    "zh_female_wenroushunv_mars_bigtts",      # Emma 温柔淑女
    "zh_female_shaoergushi_mars_bigtts",      # Tina 少儿故事
    "zh_male_silang_mars_bigtts",             # William 四郎
    "zh_male_jieshuonansheng_mars_bigtts",    # James 解说男声
    "zh_female_jitangmeimei_mars_bigtts",     # Grace 鸡汤妹妹
    "zh_female_tiexinnvsheng_mars_bigtts",    # Sophia 贴心女生
    "zh_female_qiaopinvsheng_mars_bigtts",    # Mia 俏皮女生
    "zh_female_mengyatou_mars_bigtts",        # Ava 萌丫头
    "zh_female_cancan_mars_bigtts",           # Luna 灿灿
    "zh_female_qingxinnvsheng_mars_bigtts",   # Olivia 清新女生
    "zh_female_linjia_mars_bigtts",           # Lily 邻家
    # Moon series (2025-05)
    "zh_female_wanwanxiaohe_moon_bigtts",     # Isabella 台湾腔
    "zh_male_guozhoudege_moon_bigtts",        # Andrew 粤语
    "zh_female_gaolengyujie_moon_bigtts",     # Charlotte 高冷御姐
    "zh_male_jingqiangkanye_moon_bigtts",     # Thomas 北京腔
    "zh_male_wennuanahu_moon_bigtts",         # Mark 温暖大叔
    "zh_female_linjianvhai_moon_bigtts",      # Lila 邻家女孩
    "zh_male_shaonianzixin_moon_bigtts",      # Ethan 少年自信
    "zh_male_yuanboxiaoshu_moon_bigtts",      # Joseph 远播小数
    "zh_female_daimengchuanmei_moon_bigtts",  # Elena 呆萌川妹
    "zh_male_yangguangqingnian_moon_bigtts",  # George 阳光青年
    "zh_female_shuangkuaisisi_moon_bigtts",   # Aria 爽快飒姐
    # Jupiter series (high quality)
    "zh_female_vv_jupiter_bigtts",            # vv 活泼灵动女声
    "zh_female_xiaohe_jupiter_bigtts",        # xiaohe 甜美台妹
    "zh_male_yunzhou_jupiter_bigtts",         # yunzhou 清爽男声
    "zh_male_xiaotian_jupiter_bigtts",        # xiaotian 磁性男声
    # Saturn series (2025-11)
    "zh_female_xueayi_saturn_bigtts",         # 儿童绘本
]

def get_voice_list(tts_provider: str = "local") -> list[str]:
    """Return available voice names based on current TTS provider."""
    if tts_provider == "volcengine":
        return VOLCENGINE_VOICE_LIST
    return OMNI_VOICE_LIST


def get_default_voice(tts_provider: str = "local") -> str:
    """Return the default voice for the given provider."""
    if tts_provider == "volcengine":
        return VOLCENGINE_VOICE_LIST[0]
    return OMNI_DEFAULT_VOICE


class AudioProcessor:
    def __init__(self, voice_config: dict | None = None):
        self.stt_model = None
        self.omni_client = Client("http://localhost:7862/")
        # voice config from Config, lazily read
        self._voice_config = voice_config or {}

    def _get_tts_provider(self) -> str:
        return self._voice_config.get("tts_provider", "local")

    def _get_stt_provider(self) -> str:
        return self._voice_config.get("stt_provider", "local")

    def _get_volcengine_cfg(self) -> dict:
        return self._voice_config.get("volcengine", {})

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
    def _detect_audio_format(audio_bytes: bytes) -> str:
        """Detect audio container format from magic bytes."""
        if audio_bytes[:4] == b'\x1a\x45\xdf\xa3':  # EBML header (WebM/Matroska)
            return "webm"
        if audio_bytes[:4] == b'RIFF':  # WAV
            return "wav"
        if audio_bytes[:3] == b'\xff\xfb' or audio_bytes[:4] == b'\xff\xf3':  # MP3
            return "mp3"
        if audio_bytes[:4] == b'ftyp':  # MP4/M4A
            return "m4a"
        return "wav"  # best guess

    def _convert_to_pcm(self, audio_bytes: bytes) -> bytes:
        """Convert audio bytes to PCM 16kHz 16-bit mono via ffmpeg."""
        proc = subprocess.Popen(
            ['ffmpeg', '-i', '-', '-f', 's16le', '-acodec', 'pcm_s16le',
             '-ar', '16000', '-ac', '1', '-loglevel', 'error', '-'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        pcm_data, stderr = proc.communicate(input=audio_bytes)
        if proc.returncode != 0:
            msg = stderr.decode('utf-8', errors='replace')[:200]
            raise RuntimeError(f"音频转码失败: {msg}")
        if not pcm_data:
            raise RuntimeError("音频转码结果为空")
        return pcm_data

    def _transcribe_volcengine(self, audio_bytes: bytes) -> dict:
        """STT via Volcengine WebSocket ASR API (大模型流式语音识别)."""
        cfg = self._get_volcengine_cfg()
        app_id = cfg.get("app_id", "")
        access_token = cfg.get("access_token", "")
        api_key = cfg.get("api_key", "")
        if not app_id or not access_token:
            return {"text": "", "duration_ms": 0, "error": "火山引擎未配置 app_id 或 access_token"}

        # Determine auth: prefer new console (api_key) over old console (app_id+access_token)
        use_api_key = bool(api_key)
        use_old_auth = bool(app_id) and bool(access_token) and not use_api_key

        if not use_api_key and not use_old_auth:
            return {"text": "", "duration_ms": 0, "error": "火山引擎未配置有效的凭据（api_key 或 app_id+access_token）"}

        # Convert audio to PCM 16kHz 16-bit mono
        try:
            pcm_data = self._convert_to_pcm(audio_bytes)
        except RuntimeError as e:
            return {"text": "", "duration_ms": 0, "error": str(e)}

        ws_url = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"

        # Use bigasr (ASR 1.0) resource — seedasr (2.0) requires separate activation
        headers = {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
        }
        if use_api_key:
            headers["X-Api-Key"] = api_key
        else:
            headers["X-Api-App-Key"] = app_id
            headers["X-Api-Access-Key"] = access_token
        header_list = [f"{k}: {v}" for k, v in headers.items()]

        try:
            ws = websocket.create_connection(ws_url, header=header_list, timeout=60)
        except Exception as e:
            return {"text": "", "duration_ms": 0, "error": f"WebSocket 连接失败: {e}"}

        # ── Binary protocol constants ──
        PROTO_VER = 0b0001
        HDR_SIZE = 0b0001  # 1 × 4 = 4 bytes
        SER_JSON = 0b0001
        COMP_GZIP = 0b0001
        MSG_FULL_REQ = 0b0001
        MSG_AUDIO = 0b0010
        FLAG_POS_SEQ = 0b0001
        FLAG_NEG_SEQ = 0b0011  # last packet

        def _header(msg_type: int, flags: int) -> bytes:
            return struct.pack(
                "!BBBB",
                (PROTO_VER << 4) | HDR_SIZE,
                (msg_type << 4) | flags,
                (SER_JSON << 4) | COMP_GZIP,
                0x00,  # reserved
            )

        try:
            seq = 1

            # ── Send FULL_CLIENT_REQUEST (config) ──
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
            frame = (
                _header(MSG_FULL_REQ, FLAG_POS_SEQ)
                + struct.pack("!i", seq)
                + struct.pack("!I", len(payload))
                + payload
            )
            ws.send_binary(frame)
            seq += 1

            # ── Send audio chunks (200ms = 6400 bytes at 16kHz/16-bit/mono) ──
            CHUNK = 16000 * 2 * 200 // 1000  # 6400
            offset = 0
            while offset < len(pcm_data):
                chunk = pcm_data[offset:offset + CHUNK]
                is_last = (offset + CHUNK >= len(pcm_data))
                f = FLAG_NEG_SEQ if is_last else FLAG_POS_SEQ
                s = -seq if is_last else seq
                compressed = gzip.compress(chunk)
                frame = (
                    _header(MSG_AUDIO, f)
                    + struct.pack("!i", s)
                    + struct.pack("!I", len(compressed))
                    + compressed
                )
                ws.send_binary(frame)
                seq += 1
                offset += CHUNK

            # ── Receive response ──
            result_text = ""
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
                    pos += 4  # skip sequence number
                pld_sz = struct.unpack("!I", raw[pos:pos + 4])[0]
                pos += 4
                pld = raw[pos:pos + pld_sz]

                if compression == COMP_GZIP:
                    pld = gzip.decompress(pld)

                body = json.loads(pld.decode("utf-8"))

                if msg_type == 0b1001:  # SERVER_FULL_RESPONSE
                    text = body.get("result", {}).get("text", "")
                    if text:
                        result_text += text
                    if body.get("result", {}).get("is_final", False):
                        break
                elif msg_type == 0b1111:  # SERVER_ERROR_RESPONSE
                    err = body.get("message", "未知错误")
                    return {"text": "", "duration_ms": 0, "error": f"火山引擎 ASR 错误: {err}"}

            return {"text": result_text.strip(), "duration_ms": 0}

        except websocket.WebSocketTimeoutException:
            return {"text": result_text.strip(), "duration_ms": 0, "error": "火山引擎 ASR 超时"}
        except websocket.WebSocketConnectionClosedException:
            # Server closed connection (audio fully processed), return what we have
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
        """TTS via local OmniVoice: text -> wav bytes. Returns (wav_bytes, 'audio/wav')."""
        voice_name = voice or OMNI_DEFAULT_VOICE
        h = hashlib.md5((text + str(speed) + voice_name).encode()).hexdigest()[:12]
        cache_path = GENERATED_DIR / f"tts_{h}.wav"
        if cache_path.exists():
            return cache_path.read_bytes(), "audio/wav"

        print(f"[TTS] Calling OmniVoice (voice={voice_name})...")

        wav_path, _ = self.omni_client.predict(
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

    def _synthesize_volcengine(self, text: str, speed: float = 1.0, voice: str | None = None) -> tuple[bytes, str]:
        """TTS via Volcengine V3 API (豆包语音合成模型2.0): text -> audio bytes."""
        cfg = self._get_volcengine_cfg()
        app_id = cfg.get("app_id", "")
        access_token = cfg.get("access_token", "")
        api_key = cfg.get("api_key", "")
        resource_id = cfg.get("resource_id", "seed-tts-2.0")
        speaker = voice or cfg.get("voice_type", "zh_female_cancan_mars_bigtts")

        # Prefer new console (X-Api-Key) over old console (X-Api-App-Id + X-Api-Access-Key)
        use_api_key = bool(api_key)
        use_old_auth = bool(app_id) and bool(access_token) and not use_api_key
        if not use_api_key and not use_old_auth:
            raise RuntimeError("火山引擎未配置 api_key（新版），或 app_id + access_token（旧版）")

        audio_format = cfg.get("audio_format", "mp3")
        h = hashlib.md5((text + str(speed) + speaker + "volc-v3").encode()).hexdigest()[:12]
        cache_ext = "mp3" if audio_format == "mp3" else "ogg"
        cache_path = GENERATED_DIR / f"tts_{h}.{cache_ext}"
        if cache_path.exists():
            mime = "audio/mpeg" if audio_format == "mp3" else "audio/ogg"
            return cache_path.read_bytes(), mime

        # Map speed 0.5-2.0 to V3 speech_rate range -50~100
        speech_rate = max(-50, min(100, int((speed - 1.0) * 100)))

        payload = {
            "user": {
                "uid": "localchat",
            },
            "req_params": {
                "text": text,
                "speaker": speaker,
                "audio_params": {
                    "format": audio_format,
                    "sample_rate": 24000,
                },
                "additions": {
                    "disable_markdown_filter": True,
                },
            },
        }

        # Apply speech_rate if not default
        if speech_rate != 0:
            payload["req_params"]["audio_params"]["speech_rate"] = speech_rate

        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        if use_old_auth:
            headers["X-Api-App-Id"] = app_id
            headers["X-Api-Access-Key"] = access_token
        else:
            headers["X-Api-Key"] = api_key

        print(f"[TTS] Calling Volcengine V3 (speaker={speaker})...")
        try:
            with httpx.Client(timeout=30.0) as cli:
                resp = cli.post(
                    VOLCENGINE_TTS_URL,
                    json=payload,
                    headers=headers,
                )
                if resp.status_code != 200:
                    detail = resp.text[:300]
                    raise RuntimeError(f"火山引擎 TTS V3 错误 (HTTP {resp.status_code}): {detail}")

                audio_bytes = resp.content

            # Verify it's actually audio by checking Content-Type
            ct = resp.headers.get("content-type", "")
            if ct and "json" in ct:
                # API returned JSON error disguised as 200
                error_text = audio_bytes.decode("utf-8", errors="replace")[:200]
                raise RuntimeError(f"火山引擎返回错误: {error_text}")

            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(audio_bytes)
            print(f"[TTS] OK ({len(audio_bytes)} bytes, speaker={speaker})")

            mime = "audio/mpeg" if audio_format == "mp3" else "audio/ogg"
            return audio_bytes, mime
        except httpx.RequestError as e:
            raise RuntimeError(f"火山引擎 TTS 请求失败: {e}")
