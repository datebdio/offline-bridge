#include <chrono>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <iomanip>
#include "sherpa-onnx/c-api/cxx-api.h"

static std::string Base64Decode(const std::string& in) {
    static const std::string chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, valb = -8;
    for (unsigned char c : in) {
        if (c == '=') break;
        auto pos = chars.find(static_cast<char>(c));
        if (pos == std::string::npos) continue;
        val = (val << 6) + static_cast<int>(pos);
        valb += 6;
        if (valb >= 0) {
            out.push_back(static_cast<char>((val >> valb) & 0xFF));
            valb -= 8;
        }
    }
    return out;
}

static std::vector<std::string> SplitTabs(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream ss(line);
    std::string item;
    while (std::getline(ss, item, '\t')) fields.push_back(item);
    return fields;
}

int main() {
    using namespace sherpa_onnx::cxx;
    const auto initStart = std::chrono::steady_clock::now();
    OfflineTtsConfig config;
    config.model.vits.model = "assets/model/model.onnx";
    config.model.vits.lexicon = "assets/model/lexicon.txt";
    config.model.vits.tokens = "assets/model/tokens.txt";
    config.model.num_threads = 2;
    config.model.provider = "cpu";
    config.rule_fsts = "assets/model/phone.fst,assets/model/date.fst,assets/model/number.fst";
    config.max_num_sentences = 1;
    OfflineTts tts = OfflineTts::Create(config);
    if (!tts.Get()) {
        std::cout << "ERROR\tmodel_init_failed\n" << std::flush;
        return 2;
    }
    const auto initEnd = std::chrono::steady_clock::now();
    const auto initMs = std::chrono::duration_cast<std::chrono::milliseconds>(initEnd - initStart).count();
    std::cout << "READY\t" << tts.NumSpeakers() << "\t" << tts.SampleRate() << "\t" << initMs << "\n" << std::flush;

    std::string line;
    while (std::getline(std::cin, line)) {
        if (line == "QUIT") break;
        const auto f = SplitTabs(line);
        if (f.size() != 5 || f[0] != "GEN") {
            std::cout << "ERROR\tbad_request\n" << std::flush;
            continue;
        }
        try {
            const int sid = std::stoi(f[1]);
            const float speed = std::stof(f[2]);
            const std::string outputPath = f[3];
            const std::string text = Base64Decode(f[4]);
            if (text.empty()) {
                std::cout << "ERROR\tempty_text\n" << std::flush;
                continue;
            }
            const auto start = std::chrono::steady_clock::now();
            GeneratedAudio audio = tts.Generate(text, sid, speed);
            const auto end = std::chrono::steady_clock::now();
            const auto elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
            if (audio.samples.empty() || audio.sample_rate <= 0) {
                std::cout << "ERROR\tgeneration_empty\n" << std::flush;
                continue;
            }
            Wave wave;
            wave.samples = std::move(audio.samples);
            wave.sample_rate = audio.sample_rate;
            if (!WriteWave(outputPath, wave)) {
                std::cout << "ERROR\twave_write_failed\n" << std::flush;
                continue;
            }
            const double duration = static_cast<double>(wave.samples.size()) / static_cast<double>(wave.sample_rate);
            const double rtf = duration > 0 ? (static_cast<double>(elapsedMs) / 1000.0) / duration : 0.0;
            std::cout << "OK\t" << elapsedMs << "\t" << std::fixed << std::setprecision(3) << duration
                      << "\t" << wave.sample_rate << "\t" << std::setprecision(4) << rtf << "\n" << std::flush;
        } catch (...) {
            std::cout << "ERROR\tgeneration_exception\n" << std::flush;
        }
    }
    return 0;
}
