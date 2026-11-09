# KiCad Panelizer

KiCad PCB 参数化拼板插件。仅复制板级 `Edge.Cuts` 外边框，添加工艺边和顶/底面 Mark 点；确认后直接写入当前 PCB，并在同目录保留带时间戳的原文件备份。

当前版本：**1.0.1**  
目标环境：**KiCad 8.0 ~ 11（SWIG Action Plugin）**  
本机实测环境：**KiCad Huaqiu 10.0.6**

## 功能

- 参数化列数、行数、列距、行距。
- V 割拼板：只阵列 `Edge.Cuts` 外边框。
- 原始单板上的封装、焊盘、走线、铜皮和丝印保留在首片，不复制到其他拼板单元。
- 左、右、上、下工艺边可独立启用，默认左右各 6 mm。
- Mark 点默认 1 mm 铜、3 mm 阻焊开窗、居中放置于工艺边。
- 顶层 Mark 默认距进板边 10 mm；底层 Mark 默认距末端 15 mm。
- 对话框实时预览拼板尺寸、工艺边和 Mark 位置。
- 中文/English 界面，可跟随系统或手动切换。
- 写入前保存当前 PCB 并生成 `*.backup-YYYYMMDD-HHMMSS.kicad_pcb`。
- 防止对同一 PCB 重复拼板；重新拼板前请从备份恢复。

## 安装

### PCM 从文件安装

1. 在本仓库运行：

   ```powershell
   & 'D:\KiCad\10.0\bin\python.exe' package.py
   ```

2. 打开 KiCad → 插件和内容管理器 → **从文件安装...**
3. 选择 `dist/kicad-panelizer.zip`
4. 重启 KiCad 或刷新外部插件

生成的 ZIP 根目录包含 `metadata.json`、`plugins/` 和 `resources/`，符合 KiCad PCM 包结构。

### PCM 自定义仓库

`package.py` 会同时生成：

- `docs/packages.json`
- `repository.json`

仓库公开并创建对应 GitHub Release 后，可将 `repository.json` 的原始地址添加为 PCM 自定义仓库。

### 本地开发

开发时可将 `plugins` 目录复制到：

```text
%APPDATA%\kicad\10.0\plugins\com.github.YonimoC.kicad-panelizer
```

然后执行 **工具 → 外部插件 → 刷新插件**。

## 使用

1. 在 PCB 编辑器中保存当前板，并确保外框位于板级 `Edge.Cuts`。
2. 点击工具栏 **PCB 参数化拼板**。
3. 设置阵列、工艺边和 Mark 参数。
4. 检查右侧预览。
5. 点击 **应用并保存**。

插件会先保存当前 PCB，再创建备份，随后修改当前文件并保存拼板。

## 拼板规则

### 外边框

插件只读取当前 PCB 根部的板级 `Edge.Cuts` 图元，并把它们复制到其余阵列单元。阵列外的板内内容不会复制。

矩形板建议使用四段直线；圆弧、圆形、矩形和多边形等根级 `Edge.Cuts` 图元会原样复制。

### V 割

当前版本以阵列后的 `Edge.Cuts` 轮廓表达 V 割边界。列距为 0 时，相邻板共享边框只保留一条，避免重复 Gerber 线。行距、列距均可调整。

### Mark 点

- 铜：圆形 SMD，默认直径 1 mm。
- 阻焊：局部开窗扩展，默认总开窗直径 3 mm。
- 每个启用的侧工艺边放置两个 Mark：一个顶层、一个底层。
- 顶层 Mark 位于拼板前进方向起点后 `10 mm`。
- 底层 Mark 位于拼板末端前 `15 mm`。
- Mark 的轨宽方向位置固定为工艺边中心。

## 文件结构

```text
kicad-panelizer/
├── plugins/
│   ├── __init__.py
│   ├── kicad_panelizer.py   # Action Plugin + wxPython GUI
│   ├── panelizer.py         # KiCad 图元生成、备份与保存
│   ├── geometry.py          # 无 KiCad 依赖的阵列/工艺边/Mark 几何
│   └── i18n.py              # 中文/English 翻译
├── resources/
└── icon.png
├── tests/
├── metadata.json
├── package.py
├── repository.json
└── README.md
```

## 测试

纯几何与翻译测试：

```powershell
python -m unittest discover -s tests -p 'test_geometry.py'
```

KiCad API 集成测试：

```powershell
& 'D:\KiCad\10.0\bin\python.exe' -m unittest discover -s tests -p 'test_integration.py' -v
```

## English summary

KiCad Panelizer is a parameterized PCB panelization Action Plugin. It copies only board-level `Edge.Cuts` outlines, adds process rails and 1 mm copper / 3 mm mask fiducials on both sides, saves a timestamped backup, then replaces and saves the current PCB. The UI supports Chinese and English.

## License

MIT

## 版本历史

- **1.0.1** — 修复 Mark 焊盘保存后回到原点的问题；隐藏重复拼板标记；DRC 清零。
- **1.0.0** — 首个版本：V 割外框阵列、工艺边、顶/底面 Mark、备份、中英文界面。

