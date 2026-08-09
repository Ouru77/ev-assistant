# E.V. — Kişisel Sesli Asistan

> *A local, private voice assistant with a cyber "PC-dashboard" HUD — inspired by Peter Parker's AI **E.V.** in Spider-Man: Brand New Day.*

E.V., tamamen **kendi bilgisayarında** çalışabilen, gizliliğe önem veren bir Türkçe sesli asistandır. Konuşursun ya da yazarsın; o anlar, düşünür ve sesle cevap verir. Arayüzü, filmdeki gibi gösterişli hologramlar değil, **grid tabanlı siber bir terminal/dashboard** — Peter'ın atölyesindeki "bütçesiz ama dahi işi" havasında.

İsim ve karakter, *Spider-Man: Brand New Day*'deki Peter Parker'ın kendi yaptığı AI asistanı **E.V.**'den esinlenilmiştir: sakin, zeki, mucit ruhlu — Stark'ın gösterişli tekniği değil.

## ✨ Özellikler

- 🎙️ **Sesle konuş** — yerel **Whisper** ile Türkçe konuşma tanıma (offline, ücretsiz).
- 🧠 **Yerel beyin** — **Ollama** üzerinde çalışan yerel bir LLM (varsayılan `gemma2:9b`). İstersen Claude API'ye de bağlanır.
- 🔊 **Sesli cevap** — tarayıcının yerleşik sesi (ücretsiz) ya da daha doğal sonuç için **ElevenLabs**.
- 🖥️ **Siber HUD** — Electron masaüstü uygulaması: köşede **kompakt orb**, tam ekranda **dashboard** (sistem izleme, saat, hava, canlı ses dalgası, olay günlüğü, terminal girişi).
- 🎛️ **Ses dalgası çekirdeği** — sen konuşurken mikrofona, E.V. konuşurken kendi sesine göre gerçek zamanlı dalgalanan dairesel görselleştirici.
- 🌐 **Tarayıcı & ekran** — internette arama/sayfa açma (Playwright) ve ekran betimleme (opsiyonel).
- 🔒 **Gizli** — varsayılan kurulumda hiçbir veri buluta gitmez; her şey yerelde.
- 🔕 **Güvenli dinleme** — varsayılan sessiz; `Ctrl+Space` ile açılır, oyun/sohbet sırasında yanlışlıkla dinlemez.

## 🧩 Mimari

```
Mikrofon → Whisper (STT, yerel) → FastAPI sunucu
                                      │
                                Ollama (LLM, yerel/GPU)
                                      │
        ┌─────────────────────────────┼───────────────────────┐
     ElevenLabs / Tarayıcı        Playwright              Ekran Yakalama
        (TTS)                     (tarayıcı)              (opsiyonel)
                                      │
                        Electron HUD (WebSocket) ← → tarayıcı
```

- **Backend:** Python + FastAPI + WebSocket (`server.py`)
- **STT:** `faster-whisper` (yerel, CPU)
- **LLM:** Ollama (yerel) veya Anthropic Claude (opsiyonel)
- **TTS:** ElevenLabs veya tarayıcı Web Speech API
- **UI:** Electron + HTML/CSS/JS (`electron/`, `frontend/`)

## 🚀 Kurulum

**Gereksinimler:** Windows 10/11, Python 3.10+, [Ollama](https://ollama.com), (opsiyonel) Node.js — masaüstü uygulaması için.

```bash
# 1) Python bağımlılıkları
pip install -r requirements.txt
playwright install chromium

# 2) Yerel model (Ollama)
ollama pull gemma2:9b

# 3) Yapılandırma
#    config.example.json  ->  config.json   (kopyala ve düzenle)
#    Varsayılanlar tamamen ücretsiz: Ollama + Whisper + tarayıcı sesi. Anahtar gerekmez.

# 4) Çalıştır
python server.py
#    Tarayıcıda: http://localhost:8340
```

**Masaüstü uygulaması (Electron HUD):**

```bash
npm install
npm start
```

> Daha iyi ses için: [elevenlabs.io](https://elevenlabs.io)'dan ücretsiz bir API anahtarı al, `config.json`'a gir ve `tts_provider`'ı `"elevenlabs"` yap.
> Claude kalitesinde beyin için: [console.anthropic.com](https://console.anthropic.com)'dan anahtar al ve `llm_provider`'ı `"anthropic"` yap.

## 📁 Yapı

```
server.py            FastAPI sunucu (STT/LLM/TTS orkestrasyonu)
whisper_stt.py       Yerel Whisper konuşma tanıma
browser_tools.py     Playwright tarayıcı kontrolü
screen_capture.py    Ekran betimleme (opsiyonel)
frontend/            Arayüz (HUD + dashboard)
electron/            Masaüstü uygulama kabuğu
config.example.json  Örnek yapılandırma (kopyala -> config.json)
```

## 🙏 Teşekkür / Credits

Bu proje, [Julian Ivanov'un `jarvis-voice-assistant`](https://github.com/Julian-Ivanov/jarvis-voice-assistant) şablonu temel alınarak başlatılmış; ardından E.V. kimliği, yerel (Ollama + Whisper) yığın, siber dashboard ve Türkçe akış eklenerek yeniden şekillendirilmiştir.

Karakter ilhamı: *Spider-Man: Brand New Day* (E.V., seslendiren Naomi Watts). Bu bir hayran projesidir; Marvel/Sony ile bir bağlantısı yoktur.

## 📜 Lisans

Şimdilik belirtilmemiştir (tüm hakları saklıdır). *(Türev bir çalışma olduğundan, herkese açık bir lisans eklemeden önce temel şablonun koşulları netleştirilmelidir.)*
