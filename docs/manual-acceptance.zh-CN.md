# Codex 桌面版人工验收

[English](manual-acceptance.md) · **简体中文**

本清单通过自然语言对话验证已安装的插件，并核对仓库内提交的产物。任何时候都不要把服务商凭据粘贴进任务对话。

## 前提条件

1. 在 Codex 桌面版中打开本仓库的克隆目录，并确保 `china-travel-assistant` 已被禁用，这样 `plan-china-trip` 这个名字不会产生歧义。
2. 安装或刷新 `china-trip-weaver@china-trip-weaver-local`，然后新建一个任务。
3. 在仓库终端运行 `plugins/china-trip-weaver/scripts/ctw doctor`。AMap、FlyAI、VariFlight 应只显示 `configured`，不得出现任何值或长度。若某个服务商显示 missing，只接受该服务商文档中规定的无 Key／关闭行为。
4. 确认本地凭据文件是权限恰为 `600` 的普通文件。验收过程中不要打开或显示其中的值。

## 自然语言验收：北京到上海

在一个新的 Codex 任务中发送：

> 用 China Trip Weaver 读取 `demo/request.json` 和 `demo/candidates.json`。以只读方式运行实网规划，开启铁路、路线矩阵和住宿。不要预订，不要登录。校验 Trip 和 HTML，然后告诉我各服务商的健康状态、实时铁路腿数量、住宿候选数、航班对比数，以及 AMap 是否到达 MATRIX_READY。不要显示任何凭据。

通过标准：

- 任务使用了本插件的 `plan-china-trip` Skill，并以 `--rail live --mobility live --lodging live` 运行；
- Trip 与 HTML 校验都报告零错误；
- 两条带日期的铁路腿为实时数据，带有类型化票价和余票证据；
- AMap 为 `ready/live`，其 reason 中的调用次数不超过 80，且流水线包含 `MATRIX_READY`；
- 至少存在一个实时住宿候选和一个航班对比；
- 已配置的 FlyAI 与 VariFlight 不是 `missing`；存在匹配航班时 VariFlight 有状态与舒适度证据；
- 没有出现任何交易动作或凭据值。

## 自然语言验收：广州到深圳一日往返

发送：

> 用 China Trip Weaver 运行 `demo/guangzhou-shenzhen/request.json` 及其 `candidates.json` 描述的一日往返行程。使用实时铁路、路线矩阵和住宿模式，但当服务商没有返回结果时，不要编造过夜住宿或航班。校验两个输出，并报告去程／返程铁路车次和 AMap 实时路段数量。

通过标准：

- 恰好一个行程日，且当天有两条实时铁路腿；
- AMap 为 `ready/live`，至少一个实时路段，且流水线包含 `MATRIX_READY`；
- 这个不过夜的请求没有住宿候选，也没有酒店调用；
- 对这条短途航线，FlyAI 可以是 `ready/no_results`；没有航班候选时 VariFlight 可以零次业务调用；
- Trip、HTML、密钥三道门禁全部通过。

## 可复现的终端门禁

```bash
plugins/china-trip-weaver/scripts/ctw validate demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/trip.html demo/trip.json
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/candidates.json

plugins/china-trip-weaver/scripts/ctw validate demo/guangzhou-shenzhen/trip.json
plugins/china-trip-weaver/scripts/ctw validate-html demo/guangzhou-shenzhen/trip.html demo/guangzhou-shenzhen/trip.json
plugins/china-trip-weaver/scripts/ctw validate-candidates demo/guangzhou-shenzhen/candidates.json

/usr/bin/python3 scripts/scan_secrets.py
/usr/bin/python3 scripts/scan_secrets.py --credential-values
/usr/bin/python3 scripts/scan_secrets.py --credential-values --git-history
/usr/bin/python3 -m unittest discover -s tests
```

校验器或扫描器出现任何非零结果、任何被跳过的测试、把静态路线当作实时展示、把遮罩价当作数字展示、已配置的服务商显示缺失，或输出中出现凭据值，都算失败。
