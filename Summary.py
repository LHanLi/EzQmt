# encoding:gbk
import datetime, re, os, time
import numpy as np
import pandas as pd

# 每交易日summary_time(16:20)输出账户资产现金、持仓、交割、委托单以及各策略收盘持仓情况

ACCOUNT = '0000'                                                   # 填写您的账号
account_type = 'STOCK'
strategy_name = 'summary'
# 日志文件
save_loc = 'D:/cloud/monitor/QMT/summary/'                         # 填写您的结算文件（用于post分析及复杂多策略运行）保存位置
save_loc = save_loc + ACCOUNT + '/' + account_type + '/'    
summary_time = '162000'

#######################################################################################################
#############################        常用函数模块             ###########################################
#######################################################################################################



########################################### 日常io运行 ###################################################

# log 函数
def log(*txt):
    try:
        f = open(logfile,'a+', encoding='gbk')  
        f.write('%s'%datetime.datetime.now()+' '*6)  # 时间戳
        if type(txt[0])==pd.Series:
            f.write('name: %s\n'%txt[0].name)
            for i,v in txt[0].items():
                f.write(' '*32+str(i)+', '+str(v)+'\n')
        elif type(txt[0])==pd.DataFrame:
            f.write(' '.join([str(i) for i in txt[0].columns])+'\n')
            for i,r in txt[0].iterrows():
                f.write(' '*29+str(i)+': ')
                f.write(', '.join([str(j) for j in r.values])+'\n')
        else:
            write_str = ('\n'+' '*32).join([str(i) for i in txt])
            f.write('%s\n' %write_str)
        f.close()
    except PermissionError as e:
        print(f"Error: {e}. You don't have permission to access the specified file.")

########################################### 账户状态 ###################################################

# 获取持仓数据 DataFrame index:code, cash  如果没有持仓返回空表（但是有columns） 
def get_pos():
    position_to_dict = lambda pos: {
        'code': pos.m_strInstrumentID + '.' + pos.m_strExchangeID, # 证券代码 000001.SZ
        'name': pos.m_strInstrumentName, # 证券名称
        'vol': pos.m_nVolume, # 当前拥股，持仓量
        'AvailableVol': pos.m_nCanUseVolume, # 可用余额，可用持仓，期货不用这个字段，股票的可用数量
        'MarketValue': pos.m_dMarketValue, # 市值，合约价值
        'PositionCost': pos.m_dPositionCost, # 持仓成本，
    }
    position_info = get_trade_detail_data(ACCOUNT, account_type, 'position')
    pos = pd.DataFrame(list(map(position_to_dict, position_info)))
    if pos.empty:
        return pd.DataFrame(columns=['name', 'vol', 'AvailabelVol', 'MarketValue', 'PositionCost'])
    pos = pos.set_index('code')
    extract_names = ['新标准券', '国标准券']
    # , 'GC001', 'GC002', 'GC003', 'GC004', 'GC007', \
    #                 'GC014', 'GC028', 'GC091', 'GC182', \
    #                 'Ｒ-001', 'Ｒ-002', 'Ｒ-003', 'Ｒ-004', 'Ｒ-007',\
    #                'Ｒ-014', 'Ｒ-028', 'Ｒ-091', 'Ｒ-182']            # 逆回购仓位不看
    pos = pos[(pos['vol']!=0)&(~pos['name'].isin(extract_names))].copy()        # 已清仓不看
    return pos
# 获取账户状态 净值，现金
def get_account():
    acct_info = get_trade_detail_data(ACCOUNT, account_type, 'account')[0]
    return {'net':acct_info.m_dBalance, 'cash':acct_info.m_dAvailable}
# 获取订单状态 当日没有订单返回空表（但是有columns） 当天订单
def get_order():
    order_info = get_trade_detail_data(ACCOUNT, account_type, 'ORDER')
    order_to_dict = lambda o:{
        'id':o.m_strOrderSysID,
        'date': o.m_strInsertDate,
        'code': o.m_strInstrumentID+'.'+o.m_strExchangeID,
        'sub_time': o.m_strInsertTime,          # 例如 str:095620
        'trade_type': o.m_nOffsetFlag,          # 48 买入/开仓；49 卖出/平仓
        'price': o.m_dLimitPrice,               # 挂单价
        'sub_vol': o.m_nVolumeTotalOriginal,
        'dealt_vol': o.m_nVolumeTraded,
        'remain_vol': o.m_nVolumeTotal,
        # 48 未报， 49 待报， 50 已报， 51 已报待撤，52 部成待撤， 53 部撤(部成撤单），
        # 54 已撤， 55 部成， 56 已成， 57 废单(算法单执行完毕之后为废单）， 86 已确认， 255 未知
        'status':o.m_nOrderStatus,               
        'frozen':o.m_dFrozenMargin+o.m_dFrozenCommission,   # 冻结金额/保证金+手续费
        'remark':o.m_strRemark  # 订单备注
    }
    order = pd.DataFrame(list(map(order_to_dict, order_info)))
    if order.empty:
        return pd.DataFrame(columns=['id', 'date', 'code', 'sub_time', 'trade_type',\
            'price', 'sub_vol', 'dealt_vol', 'remain_vol', 'status', 'frozen', 'remark'])
    extract_codes = ['131810.SZ', '131811.SZ', '131800.SZ', '131809.SZ', '131801.SZ',\
                     '131802.SZ', '131803.SZ', '131805.SZ', '131806.SZ',\
                     '204001.SH', '204002.SH', '204003.SH', '204004.SH', '204007.SH',\
                     '204014.SH', '204028.SH', '204091.SH', '204182.SH']   # 深市、沪市逆回购代码
    order = order[(order['date']==datetime.datetime.today().strftime("%Y%m%d"))&\
                    (~order['code'].isin(extract_codes))].copy()
    order = order.set_index('id')
    return order[['date', 'code', 'sub_time', 'trade_type', 'price',\
        'sub_vol', 'dealt_vol', 'remain_vol', 'status', 'frozen', 'remark']] 
# 获取成交数据
def get_deal():
    deal_info = get_trade_detail_data(ACCOUNT, account_type, 'DEAL')
    deal_to_dict = lambda d:{
        'order_id':d.m_nRef, # 订单编号
        'id':d.m_strOrderSysID, # 合同编号
        'code': d.m_strInstrumentID + '.' + d.m_strExchangeID,
        'date':d.m_strTradeDate,
        'deal_time':d.m_strTradeTime, # 成交时间
        # 48 买入/开仓 49卖出/平仓  50 强平  51 平今  52 平昨  53 强减 
        'trade_type':d.m_nOffsetFlag, 
        'price':d.m_dPrice,
        'vol': d.m_nVolume,
        'amount': d.m_dTradeAmount,
        'remark': d.m_strRemark 
    }
    deal = pd.DataFrame(list(map(deal_to_dict, deal_info)))
    if deal.empty:
        return pd.DataFrame(columns=['id', 'order_id', 'code', 'date', 'deal_time',\
            'trade_type', 'price', 'vol', 'amount', 'remark'])
    extract_codes = ['131810.SZ', '131811.SZ', '131800.SZ', '131809.SZ', '131801.SZ',\
                     '131802.SZ', '131803.SZ', '131805.SZ', '131806.SZ',\
                     '204001.SH', '204002.SH', '204003.SH', '204004.SH', '204007.SH',\
                     '204014.SH', '204028.SH', '204091.SH', '204182.SH']   # 深市、沪市逆回购代码
    deal = deal[(deal['date']==datetime.datetime.today().strftime("%Y%m%d"))&\
                    (~deal['code'].isin(extract_codes))].copy()
    return deal[['id', 'order_id', 'code', 'date', 'deal_time',\
        'trade_type', 'price', 'vol', 'amount', 'remark']]

########################################### 其他 ###################################################

# 存储全局变量
class a():
    pass

##############################################################################################
###################################   策略   #################################################
##############################################################################################


def summary(C):
    today = datetime.datetime.now().date().strftime("%Y%m%d")
    # 账户
    acct = get_account()
    pd.Series(acct).to_csv(save_loc+'acct-'+today+'.csv')
    # 当日持仓记录 
    pos = get_pos()
    pos.to_csv(save_loc+'position-'+today+'.csv', encoding='utf_8_sig')
    # 当日委托单
    order = get_order()
    order.to_csv(save_loc+'order-'+today+'.csv')
    # 当日成交
    deal = get_deal()
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
        firststratpos = firststratpos.reset_index().set_index(['strat', 'code'])['vol']
        deal_ = deal.rename(columns={'remark':'strat'}).copy()
        deal_['vol'] = -deal_['vol']*deal['trade_type'].map(lambda x: 1 if x==48 \
                        else -1) # >0为卖出，<0为买入 
        summarydeal = deal_.groupby(['strat', 'code'])['vol'].sum().reset_index()
        summarydeal['strat'] = summarydeal.apply(lambda x: x['strat'] if x['vol']>0 \
                                else 'craft', axis=1)
        summarydeal = summarydeal.set_index(['strat', 'code'])['vol']
        firststratpos = firststratpos.add(summarydeal, fill_value=0)
        prestratpos = firststratpos[firststratpos>0].reset_index().set_index(['strat', 'code'])[['vol']]
    # 当日成交汇总
    deal_ = deal.rename(columns={'remark':'strat'}).copy()
    deal_['strat'] = deal_['strat'].replace('', 'craft')
    deal_['vol'] = deal_['vol']*deal_['trade_type'].map(lambda x: 1 if x==48 else -1)
    summarydeal = deal_.groupby(['strat', 'code'])['vol'].sum()
    # 当日策略持仓
    todaystratpos = prestratpos['vol'].add(summarydeal, fill_value=0).reset_index()
    todaystratpos['temp_sort'] = todaystratpos['strat'].apply(lambda x: 0 if x == 'craft' else 1)
    todaystratpos = todaystratpos.sort_values(by='temp_sort').set_index(['strat', 'code'])['vol']
    negativepos = todaystratpos[todaystratpos<0].copy()
    todaystratpos = todaystratpos[todaystratpos>0].copy()
    # 每一个负持仓先从craft策略持仓开始偷
    for i,v in negativepos.items():
        indexs = todaystratpos.loc[:, [i[1]], :].index
        for idex in indexs:
            remain_vol = todaystratpos.loc[idex] + v
            if remain_vol>0:
                todaystratpos.loc[idex] = remain_vol
            else:
                todaystratpos.loc[idex] = 0
                v = remain_vol
                continue
    todaystratpos = todaystratpos[todaystratpos>0].copy()
    todaystratpos.reset_index().to_csv(save_loc+'/stratpos-'+today+'.csv', index=False)
    log('summary success')


# 初始化函数 主程序
def init(C):
    # 存储全局变量
    global A
    A = a()
    # 初始化时检查文件夹，如果没有的话则创建
    if not os.path.exists(save_loc):
        os.makedirs(save_loc)
    # 交易日
    def trade_time(func):
        def wrapper(*args, **kwargs):
            today = datetime.datetime.now().date().strftime("%Y%m%d")
            now = datetime.datetime.now().time()
            if C.get_trading_dates('SH', today, today, 1, '1d'):
                return func(*args, **kwargs)
            else:
                pass
        return wrapper
    # 每日定时定点summary函数
    C.run_time('summary', "1d", "2024-01-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], \
        summary_time[4:6]), "SH") # 输出今日委托
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT 
