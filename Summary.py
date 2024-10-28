# encoding:gbk
import datetime, re, os, time
import numpy as np
import pandas as pd
import NormFUnc as NF

# 18:00总结当日交易
# 当日输出账户、持仓、交割、委托单

ACCOUNT = ''
account_type = 'STOCK'

strategy_name = 'summary'
# 日志文件
save_loc = 'D:/cloud/XtQuant/summary-' + ACCOUNT + '/' + account_type + '/'
summary_time = '162000'


##############################################################################################
###################################   策略   #################################################
##############################################################################################


def summary(C):
    today = datetime.datetime.now().date().strftime("%Y%m%d")
    # 账户
    acct = NF.get_account()
    pd.Series(acct).to_csv(save_loc+'acct-'+today+'.csv')
    # 当日持仓记录 
    pos = NF.get_pos()
    pos.to_csv(save_loc+'position-'+today+'.csv', encoding='utf_8_sig', index=False)
    # 当日委托单
    order = NF.get_order(strat=False)
    order.to_csv(save_loc+'order-'+today+'.csv', index=False)
    # 当日成交
    deal = NF.get_deal()
    deal.to_csv(save_loc+'deal-'+today+'.csv', index=False)
    # 总结当日成交更新策略持仓
    # 前日策略持仓
    stratposfiles =  [f for f in os.listdir(save_loc) if 'stratpos' in f]
    if len(stratposfiles)!=0:
        prestratpos = sorted(stratposfiles)[-1]
        prestratpos = pd.read_csv(save_loc+prestratpos).set_index(['strat', 'code'])
    else:
        # 当日买入之前持仓，对于当日成交部分，如果当日卖出则之前为对应策略持仓，如果当日买入则之前不持仓
        firststratpos = pos
        firststratpos['strat'] = 'craft'
        firststratpos = firststratpos.set_index(['strat', 'code'])['vol']
        deal_ = deal.rename(columns={'remark':'strat'}).copy()
        deal_['vol'] = -deal_['vol']*deal['trade_type'].map(lambda x: 1 if x==48 \
                        else -1) # >0为卖出，<0为买入 
        summarydeal = deal_.groupby(['strat', 'code'])['vol'].sum().reset_index()
        summarydeal['strat'] = summarydeal.apply(lambda x: x['strat'] if x['vol']>0 \
                                else 'craft', axis=1)
        summarydeal = summarydeal.set_index(['strat', 'code'])['vol']
        firststratpos = firststratpos.add(summarydeal, fill_value=0)
        prestratpos = firststratpos[firststratpos>0].copy()
    # 当日成交汇总
    deal_ = deal.rename(columns={'remark':'strat'})
    deal_['vol'] = deal_['vol']*deal['trade_type'].map(lambda x: 1 if x==48 else -1)
    summarydeal = deal_.groupby(['strat', 'code'])['vol'].sum()
    # 当日策略持仓
    todaystratpos = prestratpos['vol'].add(summarydeal, fill_value=0)
    todaystratpos = todaystratpos[todaystratpos>0].copy()
    todaystratpos.reset_index().to_csv(save_loc+'/stratpos-'+today+'.csv', index=False)



# 初始化函数 主程序
def init(C):
    # 存储全局变量
    global A
    A = a()
    # 初始化时检查文件夹，如果没有的话则创建
    if not os.path.exists(save_loc):
        os.makedirs(save_loc)
    # 每日定时定点summary函数
    C.run_time('summary', "1d", "2024-01-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], \
        summary_time[4:6]), "SH") # 输出今日委托
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT 
