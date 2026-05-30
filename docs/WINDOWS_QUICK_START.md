# CastFlux Windows 傻瓜式安装说明

这份说明给 Windows 用户使用。你不需要安装 Git、Python、ffmpeg，也不需要打开命令行。

## 1. 下载安装包

打开下载页面:

https://github.com/cybertronic23/castflux/releases/latest

下载页面里的 Windows 安装包:

```text
CastFlux_Setup_1.0.6.exe
```

如果浏览器提示“此文件不常下载”或 Windows 提示“是否允许此应用更改设备”，选择保留/允许即可。

## 2. 双击安装

双击 `CastFlux_Setup_1.0.6.exe`，按照安装窗口提示点击“下一步”。

安装包会自动准备:

- CastFlux 程序
- 私有 Python 运行环境
- 视频处理工具 ffmpeg
- 程序需要的 Python 依赖
- 桌面快捷方式

安装期间可能需要几分钟，请不要关闭窗口。

## 3. 打开 CastFlux

安装完成后，桌面会出现:

```text
CastFlux
```

以后每次使用，只需要双击这个桌面图标。

## 4. 首次启动填写授权信息

第一次打开时，CastFlux 会弹出“首次启动向导”。

请填写开发者提供给你的授权信息:

- `HF_TOKEN`
- `DEEPSEEK_API_KEY` 或其他 AI API Key

填写完成后点击保存，然后选择视频文件开始处理。

## 5. 网络慢怎么办

安装包已经尽量内置运行环境，所以安装阶段通常不需要额外下载依赖。

但首次处理视频时，语音识别和说话人分离模型可能需要联网下载。网络较慢时，请保持程序打开并等待。

如果长时间失败，请不要反复重装，直接按下面的方法把日志发给开发者。

## 6. 出错时怎么发日志

打开 CastFlux 后，点击窗口底部:

```text
打包故障日志
```

如果 CastFlux 打不开，可以从开始菜单找到:

```text
CastFlux -> 打包 CastFlux 故障日志
```

它会生成一个类似这样的文件:

```text
castflux-support-20260530-153000.zip
```

请把这个 zip 文件发给开发者。

## 7. 用户不需要做的事

你不需要:

- 安装 Git
- 安装 Python
- 安装 ffmpeg
- 配置环境变量
- 打开命令行
- 运行任何代码

只需要下载安装包，双击安装，双击桌面图标使用。
