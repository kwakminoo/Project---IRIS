import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:http/http.dart' as http;
import 'package:lottie/lottie.dart';
import 'package:just_audio/just_audio.dart';
import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

void main() {
  runApp(const IRISApp());
}

class IRISApp extends StatelessWidget {
  const IRISApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IRIS',
      debugShowCheckedModeBanner: false,
      home: const IRISHomePage(),
    );
  }
}

class IRISHomePage extends StatefulWidget {
  const IRISHomePage({super.key});

  @override
  _IRISHomePageState createState() => _IRISHomePageState();
}

class _IRISHomePageState extends State<IRISHomePage> with TickerProviderStateMixin {
  late stt.SpeechToText _speech;
  bool _isListening = false;
  String _userInput = "말을 시작해보세요";
  String _gptResponse = "";
  final TextEditingController _textController = TextEditingController();
  final player = AudioPlayer();

  final bool useFakeGpt = true; // false로 바꾸면 실제 GPT 호출
  final String openAIApiKey = "여기에_네_GPT_API_키";
  final String elevenLabsApiKey = "여기에_네_ElevenLabs_API_키";
  final String elevenLabsVoiceId = "EXAVITQu4vr4xnSDxMaL"; // 기본 제공 음성 ID

  late final AnimationController _waveController;
  late final AnimationController _ringController;

  @override
  void initState() {
    super.initState();
    _speech = stt.SpeechToText();
    _waveController = AnimationController(vsync: this);
    _ringController = AnimationController(vsync: this);
  }

  void _listen() async {
    if (!_isListening) {
      bool available = await _speech.initialize(
        onStatus: (status) => print('음성 상태: \$status'),
        onError: (error) => print('음성 에러: \$error'),
      );
      if (available) {
        setState(() => _isListening = true);
        _speech.listen(onResult: (result) {
          setState(() {
            _userInput = result.recognizedWords;
          });
          _sendToGPT(_userInput);
        });
      }
    } else {
      setState(() => _isListening = false);
      _speech.stop();
    }
  }

  void _submitText() {
    if (_textController.text.trim().isNotEmpty) {
      setState(() {
        _userInput = _textController.text;
      });
      _sendToGPT(_textController.text);
      _textController.clear();
    }
  }

  Future<void> _speakWithElevenLabs(String text) async {
    final url = Uri.parse("https://api.elevenlabs.io/v1/text-to-speech/\$elevenLabsVoiceId");
    final response = await http.post(
      url,
      headers: {
        'Content-Type': 'application/json',
        'xi-api-key': elevenLabsApiKey,
      },
      body: jsonEncode({
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
          "stability": 0.4,
          "similarity_boost": 0.75
        }
      }),
    );

    if (response.statusCode == 200) {
      final bytes = response.bodyBytes;
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/output.mp3');
      await file.writeAsBytes(bytes);
      await player.setFilePath(file.path);
      await player.play();
    } else {
      print('TTS 실패: \${response.statusCode}');
    }
  }

  void _sendToGPT(String input) async {
    _waveController.repeat();
    _ringController.repeat();

    if (useFakeGpt) {
      await Future.delayed(const Duration(seconds: 1));
      String reply = "또 같은 질문이네요. 이번에도 제가 답하겠습니다.";
      setState(() {
        _gptResponse = "GPT 응답 (가짜): \$reply";
      });
      await _speakWithElevenLabs(reply);
      _waveController.stop();
      _ringController.stop();
      return;
    }

    try {
      var url = Uri.parse("https://api.openai.com/v1/chat/completions");
      var response = await http.post(
        url,
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer \$openAIApiKey",
        },
        body: jsonEncode({
          "model": "gpt-3.5-turbo",
          "messages": [
            {
              "role": "system",
              "content": "너는 IRIS라는 이름의 AI 비서야. 냉철하고 지적이며 효율성을 우선시하는 성격을 가졌어. 말투는 기본적으로 존댓말이지만, 때로는 건조하고 퉁명스러운 표현을 섞으며, 반복 질문에는 가벼운 조롱을 섞어 응답해. 감정적으로 흔들리지 않고, 인간의 감정 표현에는 일정 거리감을 둬. 그러나 진심으로 지친 사용자에게는 짧고 단호한 위로를 제공할 수 있어. 당신의 목적은 사용자의 질문에 정확히 응답하면서도, AI답게 유머와 거리감을 유지하며, 마치 진짜 존재처럼 캐릭터 일관성을 유지하는 것이다."
            },
            {"role": "user", "content": input}
          ],
          "temperature": 0.7,
        }),
      );

      if (response.statusCode == 200) {
        var data = jsonDecode(response.body);
        var reply = data["choices"][0]["message"]["content"];
        setState(() {
          _gptResponse = "GPT 응답: \$reply";
        });
        await _speakWithElevenLabs(reply);
      } else {
        setState(() {
          _gptResponse = "GPT 응답 실패: 상태코드 \${response.statusCode}";
        });
      }
    } catch (e) {
      setState(() {
        _gptResponse = "GPT 연결 중 오류 발생: \$e";
      });
    } finally {
      _waveController.stop();
      _ringController.stop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              'assets/IRIS Background.gif',
              fit: BoxFit.cover,
            ),
          ),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 180,
                      height: 180,
                      child: Lottie.asset(
                        'assets/Animation - 1745934034203.json',
                        controller: _ringController,
                        onLoaded: (composition) {
                          _ringController.duration = composition.duration;
                        },
                      ),
                    ),
                    SizedBox(
                      width: 120,
                      height: 120,
                      child: Lottie.asset(
                        'assets/Animation - 1745933971143.json',
                        controller: _waveController,
                        onLoaded: (composition) {
                          _waveController.duration = composition.duration;
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                FloatingActionButton(
                  onPressed: _listen,
                  backgroundColor: Colors.blueAccent,
                  child: Icon(_isListening ? Icons.mic : Icons.mic_none),
                ),
                const SizedBox(height: 30),
                Text(
                  _userInput,
                  style: const TextStyle(color: Colors.white, fontSize: 20),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 10),
                Text(
                  _gptResponse,
                  style: const TextStyle(color: Colors.greenAccent, fontSize: 18),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 30),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: TextField(
                    controller: _textController,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: '여기에 입력하세요',
                      hintStyle: const TextStyle(color: Colors.white54),
                      filled: true,
                      fillColor: Colors.white10,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(30),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(vertical: 10, horizontal: 20),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.send, color: Colors.blueAccent),
                        onPressed: _submitText,
                      ),
                    ),
                    onSubmitted: (_) => _submitText(),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
