# QMT自动交易及监控脚本

# 快速开始

## 账户分析（需配置Summary.py导出策略运行文件）

根据持仓/交割单备注，分析策略持仓，各策略盈亏，分标的盈亏情况。

### 初始化配置

import EzQmt as qmt

'''
summary_loc: 策略运行文件目录， outcash_list: 外部转入转出资金情况（格式：[('20250124', -10000), ]），start_date/end_date: 开始/结束时间，benchmark: 业绩比较基准
conv_stk: 转债转股条款（格式：{转债代码:(股票代码，转股价), ...}），if_hide: 是否隐藏具体金额
renamestrat: 策略合并（{订单备注1：合并后策略名称a，...}）， accnum: 资金账号
'''

acct0 = qmt.smy.account(summary_loc, outcash_list=[], start_date=None, end_date=None, benchmark=None,
conv_stk={}, if_hide=True, renamestrat={}, accnum='')

### 总账户

'''
总组合净值，月度收益，收益的标的贡献
'''

acct0.pnl()

![image](https://github.com/user-attachments/assets/f044754e-8e49-4145-8e16-c9f683650a2f)

![image](https://github.com/user-attachments/assets/5377d28a-f8be-4584-8677-fa6d7b5d5761)

acct0.pnl_monthly()

![image](https://github.com/user-attachments/assets/5ee0e60e-8ea2-476d-8079-ba9b2f088155)

acct0.contri['all']

![image](https://github.com/user-attachments/assets/04c8617a-4990-4e0a-a0cb-a5b2f706db57)


### 分策略

'''
策略仓位，各策略表现
'''

acct0.displaystrats_pos()

acct0.displaystrats_pnl()

![image](https://github.com/user-attachments/assets/385a996c-8d64-4ce6-b488-298251ae8d03)
![image](https://github.com/user-attachments/assets/b25c20d3-9071-4a10-8468-593d1258f9c6)
'''
查看具体某一策略
'''

strat = '策略0'

acct0.pnl(strat, benchmark=None)

acct0.contri[strat]

![image](https://github.com/user-attachments/assets/ed40a08e-5a8b-471c-8961-5680fbabba2e)

![image](https://github.com/user-attachments/assets/9041d466-2ddd-412f-9461-9d4ef0fc4b02)

![image](https://github.com/user-attachments/assets/71897e1e-6c0e-4f7f-b885-1752600a6431)

### 交易滑点分析（单边）
'''
需提供分钟线数据（开盘集合竞价时间戳为9：30，9：30~9：31时间戳为9：31）
'''

deal_comm = acct0.cal_deal_comm(min_data, acct0.deal[acct0.deal['strat']=='策略1'].copy())

deal_comm[['comm_close', 'comm_open', 'comm_mco', 'comm_avg']].mean()

![image](https://github.com/user-attachments/assets/2675f059-20b8-4efd-8550-ac9ac52d1fdb)


## 策略
### Rebalance.py 仓位再平衡策略

自动拆单、挂撤单，将持仓市值占比调整至目标值。

输入为lude（禄得）格式的策略篮子文件，支持阈值调仓。


# 安装/配置

## python库安装

pip install FreeBack

pip install EzQmt

## QMT 客户端 配置方法
![1731993271869](https://github.com/user-attachments/assets/d7852645-305f-4b93-ba9c-87d1a0643e9d)

在模型研究界面，使用策略文件中内容替换图示代码框中全部代码，调整代码中自定义参数，新建策略。
![1731993357372](https://github.com/user-attachments/assets/d7a5f601-cd73-4daa-a150-55ff65418a2f)
![1731993389345](https://github.com/user-attachments/assets/0481d6f8-5814-4b2a-b9b8-50345dd450f3)

在模型交易界面，找到刚刚新建的策略，新建策略交易，选择自己的账号和账号类型，运行。

# 备注


# -------------------- 联系作者 ---------------------
对于个性化程序交易策略代码需求，可以联系作者。
![cde0c826807b3836377d0e13cf4bbf4](https://github.com/user-attachments/assets/3954cec9-8d4e-481c-a014-2ec971ab7cb4)

