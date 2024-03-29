# encoding:gbk
import datetime, re, time, copy
import numpy as np
import pandas as pd

# 1.  每交易日9:00读取策略目标权重, 如果没有目标权重文件则跳过当天交易,extract_list中标的不参与交易。
#         策略目标权重文件格式为 code，权重, 需包含全部持仓，对于不在code中的持仓视为清仓
#         文件名为日期+'-'+strat_file_name(例如，2024-01-11-strat_adv.txt, 放置于strat_file_loc目录下
# 如果没有此文件则跳过当天交易。
# 2.  start(9:30)读取持有仓位市值,与目标权重比较，确定标的买卖方向
# 3.  每隔interval(5s)，检查当前持仓与目标持仓差距，如果小于目标仓位挂买单，大于目标仓位则挂买单，买卖单按照
# 最小变动金额拆单，计算当前剩余可挂单次数，均匀挂单。
#         每次挂单比较当前持仓比例与目标比例差距，如果:
#           a.与目标仓位的金额差距小于最小变动金额的一半;
#           b.超卖、超买;
#           c.完全卖出该标的。 
#               则完成此标的交易
#         每秒检查当前挂单，如果：
#           a. 订单存在超过wait_dur(9s)未成;
#           b. 挂单价格在最新买3卖3之外。
#               则撤单
# 4. 所有标的完成交易后，可能会有剩余现金，重复3，只买入不卖出。 如果没有在end（9：55）之前完成所有标的交易（可以
# 通过调整挂单激进度，轮询间隔，立即
# 进入只买入不卖出阶段，end2（10：00）前结束。
# 5.  summary_time(151000)总结成交张数，输出结束时持仓权重。

ACCOUNT = '55010428'
account_type = 'STOCK'
multiples = 10   # 可转债最小挂单十张
strategy_name = 'target_batch_MM'
strat_file_name = 'strat_adv.txt'
strat_file_loc = 'D:/cloud/monitor/strat/'
logfile = 'D:/cloud/monitor/LogRunning/' + ACCOUNT + '-' + strategy_name + '.txt' 

extract_list = []

interval = 5   # 交易员轮询间隔3s
wait_dur = 9   # 订单发出8s后撤单
start = '093000'
end = '095500'
end2 = '100000'
summary_time = '151000'
# 最小变动金额
delta_min = 3000
# 最大挂单张数（防止错误）
max_sub_vol = 200



##############################################常用功能模块########################################



# logfile

# log函数
def log(message, write_time=True):
    with open(logfile, 'a') as f:
        if write_time:
            f.write(str(datetime.datetime.now())+'\n')
        if type(message)==type('string'):
            f.write(message)
            f.write('\n')
        elif type(message)==type(pd.Series()):
            for i,v in message.items():
                f.write(str(i)+','+str(v))
                f.write('\n')
        else:
            f.write("unable to identify message type\n")
# 获取行情快照数据 DataFrame, index:code 
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
    ## 展示列 最新价，当日成交额、成交量(张）、最高价、最低价、开盘价 
    # 盘口 askp\askv*/bid* 买卖5档， 昨收
    ## 中间价 askp\askv*/bid* 买卖5档
    display_columns = ['code', 'lastPrice', 'amount', 'pvolume', 'high', 'low', 'open', 'lastClose',\
        'mid', 'askp1', 'askp2', 'askp3', 'askp4', 'askp5', \
            'bidp1', 'bidp2', 'bidp3', 'bidp4', 'bidp5', \
            'askv1', 'askv2', 'askv3', 'askv4', 'askv5',\
              'bidv1', 'bidv2', 'bidv3', 'bidv4', 'bidv5']
    df = df[display_columns].rename(columns={'pvolume':'vol'})
    df = df.set_index('code')
    return df
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
# 从订单成交情况
def get_dealt():
    order = get_order().reset_index()
    if order.empty:
        return pd.Series()
    # 所有已撤、部成、已成订单
    dealt_total = order[order['status'].map(lambda x: x in [52, 53, 54, 55, 56])].copy()
    # 买入\卖出
    bought_vol = dealt_total[dealt_total['trade_type']==48][['dealt_vol', 'code']].groupby('code').sum()
    sold_vol = -dealt_total[dealt_total['trade_type']==49][['dealt_vol', 'code']].groupby('code').sum()
    # 完成量 有可能出现日内反向交易
    dealt_vol = pd.concat([bought_vol['dealt_vol'], sold_vol['dealt_vol']])
    dealt_vol = dealt_vol.groupby('code').sum()
    dealt_vol = dealt_vol.loc[abs(dealt_vol).sort_values(ascending=False).index]
    return dealt_vol
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
# 撤单 价格偏离盘口价过多的无效订单撤单 
def cancel_order_price(C):
    order = get_order()
    # 全部可撤订单
    order = order[order['status'].map(lambda x:(x!=53)&(x!=54)&(x!=56)&(x!=57))].copy()
    if not order.empty:
        # 最新价格
        codes = list(set(order['code']))
        snapshot = get_snapshot(C, codes)
        # 根据挂单价和最新价价差撤单
        #lastPrice = snapshot[['lastPrice', 'lastClose']].apply(lambda x: \
        #    x['lastPrice'] if x['lastPrice']!=0 else x['lastClose'], axis=1)
        #lastPrice = order['code'].map(lambda x: lastPrice[x])
        #if not order.empty:
        #    delta = abs((order['price']-lastPrice)/lastPrice)
        #    delta = delta[delta>r]
        #    for orderid in delta.index:
        #        cancel(orderid, ACCOUNT, account_type, C)
        # 根据盘口撤单
        ask3 = order['code'].map(lambda x: snapshot['askp3'][x])
        bid3 = order['code'].map(lambda x: snapshot['bidp3'][x])
        if not order.empty:
            # higher than ask
            hta = order['price']>ask3
            ltb = order['price']<bid3
            orderids = order['price'][hta|ltb].index
            for orderid in orderids:
                cancel(orderid, ACCOUNT, account_type, C)
#卖出 
def sell(C, code, price, vol, strategyName=strategy_name, remark=strategy_name):
    # 卖出，单标的，账号， 代码，限价单，价格，量，策略名，立即触发下单，备注
    if account_type=='STOCK':
        passorder(24, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(34, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
#买入
def buy(C, code, price, vol, strategyName=strategy_name, remark=strategy_name):
    if account_type=='STOCK':
        passorder(23, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(33, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
# 存储全局变量
class a():
    pass



################################################策略############################################



# 订单成交情况
def order_stat(C):
    order = get_order()
    # 当日没有订单
    if order.empty:
        print('no orders')
        return
    display_len = len(order.index)
    # 打印最近提交的10条订单，除非全部是部撤单/已撤/已成/废单状态
    if not order['status'].iloc[:min(5,display_len)].map(lambda x: x in [53, 54, 56, 57]).prod():
        print(order.iloc[:min(5,display_len)][['code', 'sub_time', 'price', 'remain_vol', 'status']])

# 读取策略目标权重文件
def read_weight(C):
    #A.today = datetime.datetime.today().strftime('%y%m%d')
    A.today = datetime.datetime.today()
    # 读取每日转债目标仓位
    filename = strat_file_loc+'%s-'%str(datetime.datetime.today().date()) + strat_file_name
    try:
        A.weight = pd.read_csv(filename, index_col=0, header=None)[1]
        A.skip = False
    except:
        A.skip = True
        return
    # 不在目标中的标的目标仓位为0
    pos = get_pos()
    for i in pos['vol'].index:
        if (i not in A.weight.index) and (i not in extract_list):
            A.weight[i] = 0	
    # 记录交易完成时间
    A.trade_complete = {} 
    print('%s目标市值权重：'%A.today.date())
    print(A.weight)
    #print(A.direct)
    log('目标市值权重')
    log(A.weight, write_time=False)

# 获取交易方向
def get_direct(C):
    if A.skip:
        print('skip')
        return
    # 交易方向 1为买入 -1为卖出
    pos = get_pos()
    pos = pos.loc[[i for i in pos.index if i not in extract_list]]
    init_weight = pos['MarketValue']/pos['MarketValue'].sum()
    # 之前没有持仓的为买入
    A.direct = np.sign(A.weight - init_weight).fillna(1)
    A.trade_loop = 1
    print(A.direct)
    log('交易方向')
    log(A.direct, write_time=False)

# 挂单程序
def trader(C):
    if A.skip:
        print('skip')
        return
    # 每此操作A.weight中全部标的
    # 如果当前code的权重与A.weight权重相差金额小于最小操作金额，则将标的放入
    #start_counter = time.perf_counter()
    for code, weight in A.weight.items():
        if (code not in A.trade_complete.keys()) and (code not in extract_list):
            # 行情
            snapshot = get_snapshot(C, [code])
            lastPrice = snapshot[['lastPrice', 'lastClose']].apply(lambda x: \
                x['lastPrice'] if x['lastPrice']!=0 else x['lastClose'], axis=1)
            # 账户
            acct = get_account()
            pos = get_pos()
            # 持有张数和市值
            if code not in pos.index:
                marketvalue = 0
                available_vol = 0
                hold_vol = 0
                #print("don't hold %s"%code)
            else:
                marketvalue = pos['MarketValue'][code]
                available_vol = pos['AvailableVol'][code]
                hold_vol = pos['vol'][code]
            # 比较当前占比与目标占比
            delta_amount = acct['net']*weight-marketvalue
            # 最小交易张数对应此标的的最小变动金额
            min_vol = delta_min/lastPrice[code]
            min_vol = min_vol - min_vol%multiples + multiples
            min_amount = min_vol*lastPrice[code]
            # 如果当前比例和目标比例之间差值小于最小变动金额的一半（每次交易都是超过一些，保证不会有剩余现金），
            # 并且不清仓此标的，则对该标的的交易结束
            if (abs(delta_amount)<min_amount/2)&(weight!=0):
                A.trade_complete[code] = datetime.datetime.now()
                printstr1 = '{} success {}/{}%({}/{}), delta_amount {}, min_amount {}, min_vol {}'.format(code,\
                    round(100*marketvalue/acct['net'],2), round(100*weight,2),\
                        round(marketvalue,1), round(acct['net'],1), delta_amount,\
                            min_amount, min_vol)
                printstr2 = 'sucess {}/{}'.format(len(A.trade_complete), len(A.weight))
                print(printstr1)
                print(printstr2)
                log(printstr1)
                log(printstr2, write_time=False)
            # 清仓标的情况需要持有张数为0才结束交易
            elif (hold_vol==0)&(weight==0):
                A.trade_complete[code] = datetime.datetime.now()
                printstr1 = '{} success {}/{}%({}/{}), delta_amount {}, min_amount {}, min_vol {}'.format(code, \
                    round(100*marketvalue/acct['net'],2), round(100*weight,2),\
                        round(marketvalue,1), round(acct['net'],1), round(delta_amount,2),\
                            min_amount, min_vol)
                printstr2 = 'sucess {}/{}'.format(len(A.trade_complete), len(A.weight))
                print(printstr1)
                print(printstr2)
                log(printstr1)
                log(printstr2, write_time=False)
            # 原本买入买多了或原本卖出卖多了
            elif (delta_amount*A.direct[code])<0:
                A.trade_complete[code] = datetime.datetime.now()
                printstr1 = '{} success {}/{}%({}/{}), delta_amount {}, direct {}'.format(code, \
                    round(100*marketvalue/acct['net'],2), round(100*weight,2),\
                        round(marketvalue,1), round(acct['net'],1),round(delta_amount,2),\
                            A.direct[code])
                printstr2 = 'sucess {}/{}'.format(len(A.trade_complete), len(A.weight))
                print(printstr1)
                print(printstr2)
                log(printstr1)
                log(printstr2, write_time=False)
            # 否则进行挂单
            else:
                remain_times = 1+int((datetime.datetime.strptime(end, "%H%M%S")-datetime.datetime.now()).seconds/interval)
                # 卖出, 确保有可用股份
                if (delta_amount<0)&(available_vol!=0):
                    # 清仓
                    if weight==0:
                    # 剩余需要交易张数和挂单轮次
                        remain_vol = available_vol
                    else:
                        remain_vol = -delta_amount/lastPrice[code]
                    # 平均成交所需挂单量
                    per_vol = int(remain_vol/remain_times)
                    per_vol = per_vol - per_vol%multiples + multiples
                    #price = max(lastPrice[code], snapshot['mid'][code])
                    # 卖出报价比卖一低一厘
                    price = snapshot['bidp5'][code]
                    vol = max(per_vol, min_vol)
                    sell(C, code, price, int(min(vol, available_vol)))
                elif delta_amount>0:
                    remain_vol = delta_amount/lastPrice[code]
                    # 平均成交所需挂单量
                    per_vol = int(remain_vol/remain_times)
                    per_vol = per_vol - per_vol%multiples + multiples
                    # 均价和最优价之间有利的
                    #price = min(lastPrice[code], snapshot['mid'][code])
                    # 买入报价比买一高一厘
                    price = snapshot['askp5'][code]
                    vol = max(per_vol, min_vol)
                    if vol*price<acct['cash']:
                        if vol<max_sub_vol:
                            buy(C, code, price, int(vol))
                        else:
                            print('too fast to sub %s, %s'%(int(vol),code))
                            log('too fast to sub %s, %s'%(int(vol),code))
    #print('%d code cost'%(len(A.weight)-len(A.trade_complete)), time.perf_counter()-start_counter)

# 第二次平衡，仅买入
def trader_2(C):
    if A.skip:
        print('skip')
        return
    # 超过end时间或trader完成，并且A.trade_complete未重置
    if ((len(A.trade_complete.keys())==len(A.weight)) or \
        datetime.time(int(end[:2]), int(end[2:4]), int(end[4:6]))<=datetime.datetime.now().time()) and\
            A.trade_loop==1:
        # 只买入不卖出
        A.direct[A.direct.index] = 1
        print(A.direct)
        log('trader2')
        # 重置交易完成时间
        A.trade_complete1 = copy.copy(A.trade_complete)
        A.trade_complete = {}
        A.trade_loop = 2
    elif len(A.trade_complete.keys())!=len(A.weight):
        trader(C)

# 撤单程序
def order_canceler(C):
    cancel_order(C, wait_dur)
    cancel_order_price(C)

# 交易情况总结  (距离目标订单还需要再买(+)卖(-)多少) 
def summary_trade(C):
    #log('未成数量')
    #log(dealt_vol, write_time=False)
    dealt_vol = get_dealt()
    print('成交')
    print(dealt_vol)
    log('交易张数')
    log(dealt_vol, write_time=False)
    pos = get_pos()
    pos = pos.loc[[i for i in pos.index if i not in extract_list]]
    end_weight = pos['MarketValue']/pos['MarketValue'].sum()
    print('结束时权重')
    print(end_weight)
    log('结束时权重')
    log(end_weight, write_time=False)
    #log('结束交易时间')
    #log(pd.Series(A.trade_complete1).sort_values(), write_time=False)
    #log('结束第二次交易时间')
    #log(pd.Series(A.trade_complete).sort_values(), write_time=False)



# 初始化函数 主程序
def init(C):
    # 存储全局变量
    global A
    A = a()
    # 初始化时读取一次，之后每日8:30读取
    read_weight(C)
    # 全部交易时间
    def trade_time(func):
        def wrapper(*args, **kwargs):
            today = datetime.datetime.now().date().strftime("%Y%m%d")
            now = datetime.datetime.now().time()
            if C.get_trading_dates('SH', today, today, 1, '1d'):
                if (datetime.time(9, 30) <= now <= datetime.time(11, 30)) or \
                    (datetime.time(13, 00) <= now <= datetime.time(15, 00)):
                    return func(*args, **kwargs)
                else:
                    pass
            else:
                pass
        return wrapper
    # 交易时间运行装饰器 交易日start到end
    def trader_time(func):
        def wrapper(*args, **kwargs):
            today = datetime.datetime.now().date().strftime("%Y%m%d")
            now = datetime.datetime.now().time()
            if C.get_trading_dates('SH', today, today, 1, '1d'):
                if (datetime.time(int(start[:2]), int(start[2:4]), int(start[4:6])) \
                    <= now <= datetime.time(int(end[:2]), int(end[2:4]), int(end[4:6]))):
                    return func(*args, **kwargs)
                else:
                    pass
            else:
                pass
        return wrapper
    # 交易时间运行装饰器 交易日end到end2
    def trader2_time(func):
        def wrapper(*args, **kwargs):
            today = datetime.datetime.now().date().strftime("%Y%m%d")
            now = datetime.datetime.now().time()
            if C.get_trading_dates('SH', today, today, 1, '1d'):
                if (datetime.time(int(start[:2]), int(start[2:4]), int(start[4:6])) \
                    <= now <= datetime.time(int(end2[:2]), int(end2[2:4]), int(end2[4:6]))):
                    return func(*args, **kwargs)
                else:
                    pass
            else:
                pass
        return wrapper
   # 挂载定时函数
    global  f0, f1, f2, f3
    f0 = trade_time(order_stat)    # 订单状态输出
    C.run_time('f0', "60nSecond", "2022-08-01 09:15:00", "SH") # 60秒(20tick）运行一次
    f1 = trade_time(order_canceler)  # 定时、按条件撤单程序
    C.run_time('f1', "1nSecond", "2022-08-01 09:30:00", "SH")
    C.run_time('read_weight', "1d", "2022-08-01 09:00:00", "SH") # 每天9:00 读取组合目标权重
    # 根据交易开始时的权重确定交易方向
    C.run_time('get_direct', "1d", "2022-08-01 %s:%s:%s"%(start[:2], start[2:4], start[4:6]), "SH")
    # 第一次trader
    f2 = trader_time(trader)
    C.run_time('f2', "%snSecond"%interval, "2022-08-01 09:15:00", "SH") # 交易员
    # 第二次trader 只买入，不卖出
    f3 = trader2_time(trader_2)
    C.run_time('f3', "%snSecond"%interval, "2022-08-01 09:15:00", "SH") # 交易员
    # 总结交易
    C.run_time('summary_trade', "1d", "2022-08-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], \
        summary_time[4:6]), "SH") # 15:00 总结今日交易
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT
