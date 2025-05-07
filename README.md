# Project---IRIS

<h1 align="center">✨ IRIS - AI Voice Assistant</h1>
<p align="center">
  <img src="https://img.shields.io/badge/Flutter-3.29.3-blue?logo=flutter" />
  <img src="https://img.shields.io/badge/OpenAI-GPT--3.5-lightgrey?logo=openai" />
  <img src="https://img.shields.io/badge/Status-In%20Progress-green" />
</p>

<p align="center">
  <img src="assets/preview.gif" alt="IRIS UI Preview" width="600"/>
</p>

---

## 🧠 What is IRIS?

> IRIS는 Flutter로 제작된 인공지능 음성 비서 앱입니다.  
> Apple의 Siri, Google Assistant의 대안으로, GPT-3.5 기반의 자연어 이해와  
> 감각적인 시각화 HUD를 결합한 미래형 비서입니다.

---

## 🔥 Features

- 🎤 **실시간 음성 인식** (Speech to Text)
- 🧠 **GPT 응답 (OpenAI API)**
- 💬 **텍스트 입력 지원**
- 💠 **대화 시 반응하는 파형 애니메이션**
- 🎥 **움직이는 배경 HUD (GIF 기반 UI)**
- 📡 **멀티 플랫폼 지원 (웹 / 데스크톱 / 모바일)**

---

## 💸 수익 모델 (출시 계획)

- 🔓 **기본 기능 무료 제공**
- 🔐 **고급 기능은 구독 기반 잠금 해제**
  - GPT 고급 응답 해제
  - 기록 저장
  - 커스터마이징 기능
  - 다중 장치 동기화

> 👉 IRIS는 오픈소스로 시작되지만,  
> 출시 시점에는 **부분 유료 구독** 기능이 적용될 예정입니다.

---

## 🛠️ Tech Stack

| 기술 | 설명 |
|:--|:--|
| Flutter | 멀티플랫폼 앱 프레임워크 |
| Dart | 앱 전체 코드 베이스 |
| OpenAI API | GPT-3.5를 통한 자연어 응답 |
| speech_to_text | 음성 인식 구현 |
| lottie | 애니메이션 파형 시각화 |
| video_player | 배경 영상 지원 예정 |

---

## 🖥️ 설치 및 실행

```bash
# Flutter 설치 후
git clone https://github.com/your-username/IRIS.git
cd IRIS
flutter pub get
flutter run -d chrome
