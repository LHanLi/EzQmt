# QMT自动交易及监控脚本

## 安装

## 备注
EzQmt 文件夹中脚本适配miniqmt，需使用miniqmt调用。
EzQmt 文件夹外*.py策略可直接复制到QMT客户端运行，实现简单的必要需求。

# 主要功能

## QMT 客户端

### Summary.py 账户状态监控
总结当日账户持仓、市值、委托、成交、分策略持仓变化等信息，可实现策略分仓。

### Rebalance.py 仓位再平衡策略
自动拆单、挂撤单，将持仓市值占比调整至目标值。

### NormFunc
QMT客户端常用基础函数

## miniQMT（需运行Summary.py）

### Post.py 账户绩效后处理

