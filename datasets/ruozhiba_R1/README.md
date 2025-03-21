---
license: Apache License 2.0
text:
  conversational:
    size_scale:
      - 100-10k
    type:
      - faq
tags:
  - Alpaca
  - R1
---

## 数据集描述

### 数据集简介

使用 ruozhiba 数据集随机2000条数据用Deepseek-R1做了问答，旨在研究可能的后续微调模型任务。

（为什么只有2000条，白嫖不到多的，而且并发好慢）

数据集为 Alpaca 格式，所有思考内容均以 *\<think>\</think>*  标签输出。

## 数据集的格式和结构

### 数据格式

对数据的格式进行描述，包括数据的schema，以及提供必要的数据样本示范。本数据集采用 Alpaca 格式，每条数据包含 'instruction'（指令）、'input'（输入，可选）和 'output'（输出）。示例如下：

```
{
  "instruction": "请介绍一下Alpaca数据格式。",
  "input": "",
  "output": "Alpaca数据格式包含三个主要字段：'instruction'，'input' 和 'output'，其中'instruction'表示指令，'input'是可选的输入内容，'output'是相应的输出结果。"
}
```

## 数据集版权信息

本数据集从 [AI-ModelScope/ruozhiba](https://www.modelscope.cn/datasets/AI-ModelScope/ruozhiba) 中随机选取了2000条

