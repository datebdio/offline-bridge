// Chinese UTF-8 is sent as base64 on stdin, not through Windows ANSI argv.
#include <iostream>
#include <string>
#include <vector>
#include "sherpa-onnx/c-api/cxx-api.h"
static std::string Decode(const std::string& in) {
 static const std::string a="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 std::string out; int v=0,b=-8;
 for(unsigned char c:in) {
  if(c=='=')break;
  auto p=a.find(static_cast<char>(c)); if(p==std::string::npos)continue;
  v=(v<<6)+static_cast<int>(p);b+=6;
  if(b>=0){out.push_back(static_cast<char>((v>>b)&255));b-=8;}
 }
 return out;
}
int main() {
 using namespace sherpa_onnx::cxx;
 try{
  std::string line;if(!std::getline(std::cin,line))return 3;
  std::string text=Decode(line);if(text.empty()||text.size()>1000)return 4;
  OfflineTtsConfig c;
  c.model.vits.model="../model/model.onnx";
  c.model.vits.lexicon="../model/lexicon.txt";
  c.model.vits.tokens="../model/tokens.txt";
  c.model.num_threads=2;c.model.provider="cpu";
  c.rule_fsts="../model/date.fst,../model/number.fst";
  c.max_num_sentences=1;
  auto tts=OfflineTts::Create(c);
  if(!tts.Get()){std::cerr<<"ERROR init\n";return 5;}
  auto audio=tts.Generate(text,0,1.05f);
  if(audio.samples.empty()||audio.sample_rate<=0){std::cerr<<"ERROR empty\n";return 6;}
  Wave w;w.samples=std::move(audio.samples);w.sample_rate=audio.sample_rate;
  if(!WriteWave("speech-output.wav",w)){std::cerr<<"ERROR write\n";return 7;}
  std::cout<<"OK samples="<<w.samples.size()<<" rate="<<w.sample_rate<<"\n";
  return 0;
 }catch(const std::exception& e){std::cerr<<"ERROR "<<e.what()<<"\n";return 8;}
 catch(...){std::cerr<<"ERROR internal\n";return 9;}
}