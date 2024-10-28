# encoding:gbk
import datetime, re, os, time
import numpy as np
import pandas as pd

# 16:20总结当日交易
# 当日输出账户、持仓、交割、委托单


ACCOUNT = '55012783'       # 259800
account_type = 'STOCK'

strategy_name = 'summary'
# 日志文件
save_loc = 'D:/cloud/XtQuant/summary-' + ACCOUNT + '/' + account_type + '/'
summary_time = '162000'

#######################################################################################################
#############################        常用函数模块             ###########################################
#######################################################################################################



########################################### 日常io运行 ###################################################

# log 函数
def log(*txt):
    try:
        f = open(logfile,'a+', encoding='gbk')
        write_str = ('\n'+' '*35).join([str(i) for i in txt])
        f.write('%s,        %s\n' % \
            (datetime.datetime.now(), write_str))
        f.close()
    except PermissionError as e:
        print(f"Error: {e}. You don't have permission to access the specified file.")

# log ser函数
def log_ser(text, write_time=True):
    with open(logfile, 'a') as f:
        if type(text)==type(pd.Series()):
            for i,v in text.items():
                f.write(str(i)+','+str(v))
                f.write('\n')
        else:
            f.write("unable to identify message type\n")

########################################### 行情数据 ###################################################

# 获取行情快照数据 DataFrame, index:code 
SHmul = 10
SZmul = 10
def get_snapshot(C, code_list):
    # 获取标的快照数据
    df = C.get_full_tick(code_list)
    df = pd.DataFrame.from_dict(df, dtype='float').T.reset_index().rename(columns={'index': 'code'})
    # 盘口
    bidPrice_columns = ['bidp1','bidp2','bidp3','bidp4','bidp5']
    askPrice_columns = ['askp1','askp2','askp3','askp4','askp5']
    df[bidPrice_columns] = df['bidPrice'].apply(pd.Series, index=bidPrice_columns)
    df[askPrice_columns] = df['askPrice'].apply(pd.Series, index=askPrice_columns)
    bidVol_columns = ['bidv1','bidv2','bidv3','bidv4','bidv5']
    askVol_columns = ['askv1','askv2','askv3','askv4','askv5']
    df[bidVol_columns] = df['bidVol'].apply(pd.Series, index=bidVol_columns)
    df[askVol_columns] = df['askVol'].apply(pd.Series, index=askVol_columns)
    # 中间价
    df['mid'] = (df['bidp1'] + df['askp1'])/2
    # 涨跌停则bid/askprice为0
    df.loc[(df['bidp1'] == 0) | (df['askp1'] == 0),'mid'] = df['bidp1'] + df['askp1'] # 涨跌停修正
    ## 展示列 最新价，当日成交额、成交量(手）、最高价、最低价、开盘价 
    # 盘口 askp\askv*/bid* 买卖5档， 昨收
    ## 中间价 askp\askv*/bid* 买卖5档，需要使用券商行情
    display_columns = ['code', 'lastPrice', 'amount', 'volume', 'high', 'low', 'open', 'lastClose',\
        'mid', 'askp1', 'askp2', 'askp3', 'askp4', 'askp5', \
            'bidp1', 'bidp2', 'bidp3', 'bidp4', 'bidp5', \
            'askv1', 'askv2', 'askv3', 'askv4', 'askv5',\
              'bidv1', 'bidv2', 'bidv3', 'bidv4', 'bidv5']
    df = df[display_columns].rename(columns={'volume':'vol'})
    df = df.set_index('code')
    # 有时，沪市转债单位是手，沪市需要乘一个沪市转化因子
    df['vol'] = df['vol']*df.index.map(lambda x: SHmul if 'SH' in x else SZmul if 'SZ' in x else 1)
    return df

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

########################################### 买卖挂单 ###################################################

# 撤单 超过wait_dur s的订单取消
def cancel_order(C, wait_dur):
    order = get_order()
    # 全部可撤订单
    order = order[order['status'].map(lambda x:(x!=53)&(x!=54)&(x!=56)&(x!=57))].copy()
    if not order.empty:
        # 超过等待时间撤单 insert_time 为1900年
        order['sub_time'] = order['sub_time'].map(lambda x: datetime.datetime.strptime(x, "%H%M%S"))
        order = order[order['sub_time'].map(lambda x: (datetime.datetime.now()-x).seconds>wait_dur)]
        for orderid in order.index:
            cancel(orderid, ACCOUNT, account_type, C)
# 撤单 属于策略strat的挂单价超过最新价(1+r)或低于最新价(1-r)的订单取消
def cancel_order_price(C, r, stratname=None):
    order = get_order()
    # 全部可撤订单
    order = order[order['status'].map(lambda x:(x!=53)&(x!=54)&(x!=56)&(x!=57))].copy()
    # 属于该策略
    if stratname!=None:
        order = order[order['remark']==stratname].copy()
    if not order.empty:
        # 最新价格
        codes = list(set(order['code']))
        snapshot = get_snapshot(C, codes)
        lastPrice = snapshot[['lastPrice', 'lastClose']].apply(lambda x: \
            x['lastPrice'] if x['lastPrice']!=0 else x['lastClose'], axis=1)
        lastPrice = order['code'].map(lambda x: lastPrice[x])
        if not order.empty:
            delta = abs((order['price']-lastPrice)/lastPrice)
            delta = delta[delta>r]
            for orderid in delta.index:
                cancel(orderid, ACCOUNT, account_type, C)
#strategy_name = 'craft'
#multiples = 10
#卖出 
def sell(C, code, price, vol, strategyName=strategy_name, remark=strategy_name):
    vol = int((vol//multiples)*multiples)
    # 卖出，单标的，账号， 代码，限价单，价格，量，策略名，立即触发下单，备注
    if account_type=='STOCK':
        passorder(24, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(34, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
#买入
def buy(C, code, price, vol, strategyName=strategy_name, remark=strategy_name):
    vol = int((vol//multiples)*multiples)
    if account_type=='STOCK':
        passorder(23, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(33, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单

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
