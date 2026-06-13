"""生成测试 PDF 文件。"""
import fitz

doc = fitz.open()
page = doc.new_page()

page.insert_text(
    fitz.Point(72, 72),
    "Natural Language Processing: A Survey",
    fontname="helv", fontsize=16,
)

lines = [
    "Natural Language Processing (NLP) is a field of artificial",
    "intelligence that focuses on the interaction between computers",
    "and human language. Transformer-based models like BERT and GPT",
    "have achieved state-of-the-art results on many NLP benchmarks.",
    "",
    "Key techniques include tokenization, word embeddings, attention",
    "mechanisms, and transfer learning. The attention mechanism allows",
    "models to weigh the importance of different words in a sequence.",
    "",
    "Reinforcement learning from human feedback (RLHF) has become a",
    "standard technique for aligning large language models (LLMs) with",
    "human preferences and values.",
]

for i, line in enumerate(lines):
    if line:
        page.insert_text(fitz.Point(72, 120 + i * 22), line, fontname="helv", fontsize=11)

doc.save("/Users/sampuichan/Desktop/claude/doc-translator/tests/fixtures/sample.pdf")
doc.close()
print("Test PDF created: tests/fixtures/sample.pdf")
