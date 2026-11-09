# KiCad Panelizer

KiCad PCB 参数化拼板插件。仅复制板级 `Edge.Cuts` 外边框，添加工艺边和顶/底面 Mark 点；确认后直接写入当前 PCB，并在同目录保留一个固定的 `.kicad_pcb.bak` 原板备份。

当前版本：**1.0.4**
目标环境：**KiCad 8.0 ~ 11（SWIG Action Plugin）**  
本机实测环境：**KiCad Huaqiu 10.0.6**

## 功能

- 参数化列数、行数、列距、行距。
- V 割拼板：只阵列 `Edge.Cuts` 外边框。
- 原始单板上的封装、焊盘、走线、铜皮和丝印保留在首片，不复制到其他拼板单元。
- 左、右、上、下工艺边可独立启用，默认左右各 6 mm。
- Mark 点默认 1 mm 铜、3 mm 阻焊开窗、居中放置于工艺边。
- 顶层 Mark 默认距进板边 10 mm；底层 Mark 默认距末端 15 mm。
- 对话框实时预览每个拼板单元、编号、工艺边和 Mark 位置。
- 板框尺寸按 `Edge.Cuts` 中心线计算，不把 0.05 mm 线宽算进单板尺寸。
- 拼板完成后在 `F.SilkS` 添加横向和纵向尺寸标注，使用 KiCad 当前显示单位。
- “拼板方式”支持 **V 割拼板 / 单板模式**；单板模式原地删除插件新增的板框、工艺边和 Mark，不覆盖原板内容。
- 手动清理过阵列、但残留拼板标记的旧 PCB 可以重新拼板，不再误报“已经拼板”。
- 中文/English 界面，可跟随系统或手动切换。
- 写入前保存当前 PCB，并更新唯一的 `<原板>.kicad_pcb.bak` 备份，不再批量生成备份文件。

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

恢复单板时，将“拼板方式”切换为 **单板模式**，按钮会变成 **恢复单板并保存**。该模式只删除当前 PCB 中由插件添加的阵列板框、工艺边、Mark 和内部标记，不复制备份覆盖当前文件。

插件拼板前会先保存当前 PCB，再更新唯一的 `<原板>.kicad_pcb.bak` 备份，随后修改当前文件并保存拼板。

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

wxPython 窗口布局与模式切换测试：

```powershell
& 'D:\KiCad\10.0\bin\python.exe' -m unittest discover -s tests -p 'test_ui_layout.py' -v
```

## English summary

KiCad Panelizer is a parameterized PCB panelization Action Plugin. It copies only board-level `Edge.Cuts` outlines, adds process rails and 1 mm copper / 3 mm mask fiducials on both sides, and keeps one fixed `.kicad_pcb.bak` backup. Single-board mode removes panel-added outlines, rails, fiducials, and marker objects without replacing the board from a backup. The UI supports Chinese and English.

## License

MIT

## 版本历史

- **1.0.4** — 提升预览可读性；尺寸排除线宽；新增丝印层横纵尺寸标注；默认窗口高度避免无谓滚动。
- **1.0.3** — 新增单板恢复模式；修复旧标记导致无法重新拼板；备份改为唯一的 `.kicad_pcb.bak`。
- **1.0.2** — 对话框按屏幕尺寸自动调整，设置区支持滚动，修复窗口较小时内容被裁切。
- **1.0.1** — 修复 Mark 焊盘保存后回到原点的问题；隐藏重复拼板标记；DRC 清零。
- **1.0.0** — 首个版本：V 割外框阵列、工艺边、顶/底面 Mark、备份、中英文界面。

