# encoding:gbk
import datetime, re, os, time
import numpy as np
import pandas as pd

# 18:00总结当日交易
# 当日输出账户、持仓、交割、委托单

ACCOUNT = '55010428'
account_type = 'STOCK'


strategy_name = 'summary'
# 日志文件
save_loc = 'D:/cloud/XtQuant/summary-' + ACCOUNT + '/' + account_type + '/'
summary_time = '163000'



##############################################常用功能模块########################################



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
    return pos
# 获取账户状态 净值，现金(可用)
def get_account():
    acct_info = get_trade_detail_data(ACCOUNT, account_type, 'account')[0]
    return {'net':acct_info.m_dBalance, 'cash':acct_info.m_dAvailable}
# 获取订单状态 当日没有订单返回空表（但是有columns） 当天订单
def get_order(strat=True):
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
    if strat:
        if order.empty:
            return pd.DataFrame(columns=['code', 'sub_time', 'trade_type', 'sub_vol', 'dealt_vol', \
                  'remain_vol', 'status'])
        # 当天订单
        order = order[order['date']==datetime.datetime.today().strftime("%Y%m%d")].copy()
        # 本策略订单
        order = order[order['remark']==strategy_name].copy()
        order = order.set_index('id').sort_values('sub_time', ascending=False)
        return order[['code', 'sub_time', 'trade_type', 'price', 'sub_vol', 'dealt_vol', \
                  'remain_vol', 'status']]
    else:
        if order.empty:
            return pd.DataFrame(columns=['id', 'date', 'code', 'sub_time', 'trade_type',\
                'price', 'sub_vol', 'dealt_vol', 'remain_vol', 'status', 'frozen', 'remark'])
        order = order[order['date']==datetime.datetime.today().strftime("%Y%m%d")].copy()
        return order[['id', 'date', 'code', 'sub_time', 'trade_type', 'price',\
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
    deal = deal[deal['date']==datetime.datetime.today().strftime("%Y%m%d")].copy()
    return deal[['id', 'order_id', 'code', 'date', 'deal_time',\
        'trade_type', 'price', 'vol', 'amount', 'remark']]
# 存储全局变量
class a():
    pass



################################################策略############################################



def summary(C):
    today = datetime.datetime.now().date().strftime("%Y%m%d")
    # 账户
    acct = get_account()
    pd.Series(acct).to_csv(save_loc+'acct-'+today+'.csv')
    # 当日持仓记录 
    pos = get_pos()
    pos.to_csv(save_loc+'position-'+today+'.csv', encoding='utf_8_sig', index=False)
    # 当日委托单
    order = get_order(strat=False)
    order.to_csv(save_loc+'order-'+today+'.csv', index=False)
    # 当日成交
    deal = get_deal()
    deal.to_csv(save_loc+'deal-'+today+'.csv', index=False)

# 初始化函数 主程序
def init(C):
    # 存储全局变量
    global A
    A = a()
    # 初始化时检查文件夹，如果没有的话则创建
    if not os.path.exists(save_loc):
        os.makedirs(save_loc)
    # 每日定时定点summary函数
    C.run_time('summary', "1d", "2022-08-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], \
        summary_time[4:6]), "SH") # 输出今日委托
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT 
