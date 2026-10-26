# biaslens

**用可统计的方式看评测集里的分组差异。**

`biaslens` —— 按人群或场景分组统计评测结果，标出组间差距与样本量不足的分组。

- 零依赖，Python 3.10+ 标准库即可运行
- 单文件，`biaslens.py` 拷走就能用
- 不联网、不写文件

<!-- ipos:install -->
## 安装

零依赖，Python 3.10+ 即可：

```bash
pip install store77cam-biaslens
```

装完直接用命令名调用：

```bash
biaslens --help
```

也可以不用安装，直接把 `biaslens.py` 拷走用——它只依赖标准库。

## 为什么需要它

偏差工具多只报总体差异；biaslens 强制标注每组的样本量，不足时拒绝给出结论。

它遵守下面几条自己定的规矩：

1. **样本量不够，就别下结论**。工具直接把样本量写在结论旁边，不足的组拒绝给出结论。
2. **分组差异要带区间**。给点估计不给区间，等于没给。
3. **多重比较要提示**。组一多，随机出现「有差异」很正常。

## 用法

```bash
python biaslens.py --results results.jsonl --group gender --metric score
python biaslens.py --results results.jsonl --group gender --metric score --json
```

加 `--json` 可以拿到机器可读的结果，便于接到流水线里。

## 已知局限

- 子群体靠外部标注划分，工具不推断身份。
- 样本量不足时直接标为不可判，不给结论。
- 只报差异，不做显著性检验，也不解释成因。

## 跑测试

```bash
python test_biaslens.py
```

测试用独立的断言与临时数据，不污染工作目录。

## 来源与参考

- Python 标准库文档：<https://docs.python.org/3/>
- GitHub 仓库：<https://github.com/store77cam/biaslens>

---

## 关于作者

store77cam 做评测结果的分组差异相关的问题。这个工具先替你回答一个具体问题，再谈别的。

- 个人主页：<https://store77cam.github.io>
- 仓库：<https://github.com/store77cam/biaslens>

## 许可

MIT，见 [LICENSE](LICENSE)。
