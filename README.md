# QMT自动交易及监控脚本

## 安装

### QMT 客户端 配置方法
![1731993271869](https://github.com/user-attachments/assets/d7852645-305f-4b93-ba9c-87d1a0643e9d)

在模型研究界面，使用.py文件中内容替换图示代码框中全部代码，调整代码中自定义参数，新建策略。
![1731993357372](https://github.com/user-attachments/assets/d7a5f601-cd73-4daa-a150-55ff65418a2f)
![1731993389345](https://github.com/user-attachments/assets/0481d6f8-5814-4b2a-b9b8-50345dd450f3)

在模型交易界面，找到刚刚新建的策略，新建策略交易，选择自己的账号和账号类型，运行。

## 备注
EzQmt 文件夹中脚本除post模块外，适配miniqmt，需使用miniqmt调用。
EzQmt 文件夹外*.py策略可直接复制到QMT客户端运行，实现简单的必要需求。

# 主要功能

## QMT 客户端

### Summary.py 账户状态监控
总结当日账户持仓、市值、委托、成交、分策略持仓变化等信息，可实现策略分仓。

### Rebalance.py 仓位再平衡策略
自动拆单、挂撤单，将持仓市值占比调整至目标值。
输入为lude格式的策略篮子文件，支持阈值调仓。

### NormFunc
QMT客户端常用基础函数

## EzQmt（需在QMT客户端运行Summary.py监控账户状态）

### Post.py 账户绩效后处理

整体组合表现：
![image](https://github.com/user-attachments/assets/5235e3f3-baa0-44d8-b962-94f498ee66dc)
![image](https://github.com/user-attachments/assets/9ddf9826-e874-4722-bea7-c0d6565b9355)

分策略表现：
![image](https://github.com/user-attachments/assets/d9d476b8-2de2-487f-9a7f-4d28e5f77f62)


交易滑点分析：
![image](https://github.com/user-attachments/assets/2790b70e-2011-40d1-9a2d-2e9cb05a30fc)


