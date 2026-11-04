// WinRT/OneCore Windows speech tester helper. Windows 10/11 x64.
#include <winrt/base.h>
#include <winrt/Windows.Media.SpeechSynthesis.h>
#include <winrt/Windows.Storage.Streams.h>
#include <string>
#include <vector>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <cstdint>
using namespace winrt;
using namespace Windows::Media::SpeechSynthesis;
using namespace Windows::Storage::Streams;

static std::string sanitize(const std::string& s) {
    std::string o;
    for (unsigned char c: s) {
        if (c=='\t' || c=='\r' || c=='\n') o.push_back(' ');
        else o.push_back(static_cast<char>(c));
    }
    return o;
}
int wmain(int argc, wchar_t* argv[]) {
    if (argc < 3) return 10;
    try {
        init_apartment(apartment_type::multi_threaded);
        if (std::wstring(argv[1]) == L"list") {
            std::ofstream out(std::filesystem::path(argv[2]), std::ios::binary);
            if (!out) return 11;
            auto voices = SpeechSynthesizer::AllVoices();
            for (auto v : voices) {
                out << sanitize(to_string(v.Id())) << '\t'
                    << sanitize(to_string(v.DisplayName())) << '\t'
                    << sanitize(to_string(v.Language())) << '\t'
                    << (v.Gender()==VoiceGender::Female ? "Female" : "Male") << "\n";
            }
            return 0;
        }
        if (std::wstring(argv[1]) == L"speak") {
            if (argc != 6) return 12;
            std::wstring id=argv[2], text=argv[3];
            std::filesystem::path filename(argv[4]);
            if (text.empty()) return 13;
            SpeechSynthesizer synth;
            bool found=false;
            for(auto v: SpeechSynthesizer::AllVoices()) {
                if(std::wstring(v.Id().c_str())==id) {
                    synth.Voice(v); found=true; break;
                }
            }
            if(!found) return 14;
            SpeechSynthesisStream stream=synth.SynthesizeTextToStreamAsync(hstring(text)).get();
            uint64_t size=stream.Size();
            if(size<44 || size>50ULL*1024*1024) return 15;
            DataReader reader(stream.GetInputStreamAt(0));
            if(reader.LoadAsync(static_cast<uint32_t>(size)).get()!=size) return 16;
            std::vector<uint8_t> bytes(static_cast<size_t>(size));
            reader.ReadBytes(array_view<uint8_t>(bytes.data(),bytes.data()+bytes.size()));
            std::ofstream out(filename,std::ios::binary);
            if(!out) return 17;
            out.write(reinterpret_cast<const char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
            if(!out) return 18;
            return 0;
        }
        return 19;
    } catch (const hresult_error& e) {
        std::wcerr << L"WINRT HRESULT=" << std::hex << static_cast<uint32_t>(e.code().value) << std::endl;
        return 20;
    } catch (...) {return 21;}
}
