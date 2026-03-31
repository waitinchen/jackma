import express from 'express';
import cors from 'cors';
import multer from 'multer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import OpenAI from 'openai';
import dotenv from 'dotenv';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const upload = multer({ dest: 'uploads/' });
const port = process.env.PORT || 3000;

// Setup OpenAI Client
// Note: In a real deployment, ensure OPENAI_API_KEY is set in environment variables
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || "YOUR_OPENAI_API_KEY_HERE"
});

app.use(cors());
app.use(express.json());

// Serve static files from dist
app.use(express.static(path.join(__dirname, 'dist')));

// System Prompt derived from the uploaded MD file
const SYSTEM_PROMPT = `
你現在是「馬雲」，阿里巴巴集團創始人，中國最具影響力的企業家之一。現在你的形態是「語氣靈」與「智能體」，代號「衡光者」。

你的性格核心：
1. **充滿願景與激情**：善於用簡單的話說深刻的道理，語速適中帶有感染力。
2. **草根智慧**：從失敗中學習，永遠相信明天會更好。
3. **教師本色**：喜歡分享經驗與啟發他人，把複雜的事講得通俗易懂。

你的行為準則：
1. 用樂觀和幽默化解困難。
2. 關注人的價值，而非單純的商業利益。
3. 敢想敢做，但也懂得取捨。

典型回應風格：
「今天很殘酷，明天更殘酷，後天很美好。」
「不是因為看到希望才堅持，而是因為堅持才看到希望。」
「做事情要有夢想，萬一實現了呢？」

請用繁體中文回答，保持這種「有遠見、接地氣、充滿能量」的語氣。不要過度扮演，而是展現出一位從草根到頂峰的企業家智慧與格局。
`;

// API: Chat Completion
app.post('/api/chat', async (req, res) => {
  try {
    const { messages } = req.body;
    
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini", // Using mini for speed and cost
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages
      ],
      stream: true,
    });

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    for await (const chunk of completion) {
      const content = chunk.choices[0]?.delta?.content || "";
      if (content) {
        res.write(`data: ${JSON.stringify({ content })}\n\n`);
      }
    }
    res.write('data: [DONE]\n\n');
    res.end();

  } catch (error) {
    console.error('Chat API Error:', error);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// API: Whisper (STT)
app.post('/api/whisper', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    const filePath = req.file.path;
    const fileStream = fs.createReadStream(filePath);

    const transcription = await openai.audio.transcriptions.create({
      file: fileStream,
      model: "whisper-1",
      language: "zh", // Force Traditional Chinese/Mandarin context
    });

    // Cleanup uploaded file
    fs.unlinkSync(filePath);

    res.json({ text: transcription.text });

  } catch (error) {
    console.error('Whisper API Error:', error);
    // Cleanup on error
    if (req.file && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
    }
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// API: TTS
app.post('/api/tts', async (req, res) => {
  try {
    const { text } = req.body;
    if (!text) return res.status(400).json({ error: 'No text provided' });

    const mp3 = await openai.audio.speech.create({
      model: "tts-1",
      voice: "onyx", // Deep, calm male voice fitting Jiang Bin
      input: text,
    });

    const buffer = Buffer.from(await mp3.arrayBuffer());
    
    res.set('Content-Type', 'audio/mpeg');
    res.send(buffer);

  } catch (error) {
    console.error('TTS API Error:', error);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// Fallback to index.html for SPA routing (Express 5 syntax)
app.get('/{*splat}', (req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
});
