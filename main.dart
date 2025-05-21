import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:http/http.dart' as http;
import 'package:lottie/lottie.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'dart:convert';

void main() {
  runApp(IRISApp());
}

class IRISApp extends StatelessWidget {
  const IRISApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IRIS',
      debugShowCheckedModeBanner: false,
      home: IRISHomePage(),
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
  late FlutterTts _flutterTts;
  bool _isListening = false;
  String _userInput = "말을 시작해보세요";
  String _gptResponse = "";
  final TextEditingController _textController = TextEditingController();

  final bool useFakeGpt = true; // 나중에 false로 전환
  final String openAIApiKey = "여기에_API_KEY";

  late final AnimationController _waveController;

  @override
  void initState() {
    super.initState();
    _speech = stt.SpeechToText();
    _flutterTts = FlutterTts();
    _waveController = AnimationController(vsync: this);
  }

  void _speak(String text) async {
    await _flutterTts.setLanguage("ko-KR");
    await _flutterTts.setPitch(1.0);
    await _flutterTts.awaitSpeakCompletion(true);

    _waveController.repeat(); // GPT 말 시작
    await _flutterTts.speak(text);
    _waveController.stop();   // GPT 말 종료
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

  void _sendToGPT(String input) async {
    if (useFakeGpt) {
      await Future.delayed(Duration(seconds: 1));
      setState(() {
        _gptResponse = "GPT 응답 (가짜): \"$input\"에 대한 대답입니다.";
      });
      _speak(_gptResponse);
    } else {
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
              {"role": "user", "content": input}
            ],
            "temperature": 0.7,
          }),
        );

        if (response.statusCode == 200) {
          var data = jsonDecode(response.body);
          var reply = data["choices"][0]["message"]["content"];
          setState(() {
            _gptResponse = reply;
          });
          _speak(reply);
        } else {
          setState(() {
            _gptResponse = "GPT 응답 실패: 상태코드 \${response.statusCode}";
          });
          _speak(_gptResponse);
        }
      } catch (e) {
        setState(() {
          _gptResponse = "GPT 오류 발생: \$e";
        });
        _speak(_gptResponse);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: SingleChildScrollView(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 150,
                height: 150,
                child: Lottie.asset(
                  'assets/Animation - 1745933971143.json',
                  controller: _waveController,
                  onLoaded: (composition) {
                    _waveController.duration = composition.duration;
                  },
                ),
              ),
              SizedBox(height: 20),
              FloatingActionButton(
                onPressed: _listen,
                backgroundColor: Colors.blueAccent,
                child: Icon(_isListening ? Icons.mic : Icons.mic_none),
              ),
              SizedBox(height: 30),
              Text(
                _userInput,
                style: TextStyle(color: Colors.white, fontSize: 20),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: 10),
              Text(
                _gptResponse,
                style: TextStyle(color: Colors.greenAccent, fontSize: 18),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: 30),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: TextField(
                  controller: _textController,
                  style: TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: '여기에 입력하세요',
                    hintStyle: TextStyle(color: Colors.white54),
                    filled: true,
                    fillColor: Colors.white10,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(30),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: EdgeInsets.symmetric(vertical: 10, horizontal: 20),
                    suffixIcon: IconButton(
                      icon: Icon(Icons.send, color: Colors.blueAccent),
                      onPressed: _submitText,
                    ),
                  ),
                  onSubmitted: (_) => _submitText(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
