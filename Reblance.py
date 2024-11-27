# encoding:gbk
import datetime, re, time, os, copy
import numpy as np
import pandas as pd

#######################################################################################################
#############################        自定义参数             ###########################################
#######################################################################################################

# 1. 每天start_time前1分钟读取strat_file文件，获取目标调仓目标权重；
# 2. start_time计算当前各标的持仓市值与目标市值所需要交易金额，制定交易计划；
# 3. start_time开始交易，根据策略市值和调仓目标权重交易，多卖少买，在end_time前结束交易；
# 4. summary_time总结交易结果（该时点策略市值与持仓权重）。

# 基本设置
ACCOUNT = ''            # 填写您的账号
account_type = 'STOCK'
multiples = 10                                              # 可转债每手十张
strategy_name = 'rebalancing'                               # 策略名称
logloc = 'D:/cloud/monitor/QMT/LogRunning/'                 # 您的日志文件位置
logfile = logloc + ACCOUNT + '-' + strategy_name + '.txt'  

# 策略输入         
stratfile_loc = 'D:/cloud/monitor/strat/'                    # 您的lude篮子文件存储位置
stratfile_name = 'basket'                 # 按照 strat_file_loc+日期（20240102)-strat_file_name 格式输入策略文件
extract_codes = []                        # ！！！此篮子外的标的可能被卖出！！！
buy_num = 5                               # 此排名内买入
holding_num = 6                           # 此排名内不卖出

# 交易设置
strat_cap = 100e4           # 全部篮子标的目标市值
start_time = '143000'      # 开始交易时点
interval = 30              # 每隔interval秒挂单一次
dur_time = 300             # 最长交易时间（秒）
wait_dur = interval*0.8    # 订单等待wait_dur秒后未成交撤单
tolerance = 0.01           # 买卖挂单超价（%）
delta_min = 3000           # 最小挂单金额
delta_max = 30000          # 最大挂单金额
max_upndown = 0.2          # 涨跌幅限制，转债20%


prepare_time = datetime.datetime.strptime(start_time, "%H%M%S")\
      + datetime.timedelta(seconds=-60)  # 交易前一分钟读取篮子文件
prepare_time = prepare_time.strftime("%H%M%S")
end_time = datetime.datetime.strptime(start_time, "%H%M%S")\
      + datetime.timedelta(seconds=dur_time)
end_time = end_time.strftime("%H%M%S")
summary_time = datetime.datetime.strptime(end_time, "%H%M%S")\
      + datetime.timedelta(seconds=60)    # 交易结束后一分钟总结交易结果
summary_time = summary_time.strftime("%H%M%S")



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

# 获取账户状态 净值，现金
def get_account():
    acct_info = get_trade_detail_data(ACCOUNT, account_type, 'account')[0]
    return {'net':acct_info.m_dBalance, 'cash':acct_info.m_dAvailable}
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
    pos = pos[(pos['vol']!=0)&(~pos['name'].isin(extract_names))].copy()  # 已清仓不看，去掉逆回购重复输出
    return pos
# 忽略逆回购订单、交割单
status_extract_codes = ['131810.SZ', '131811.SZ', '131800.SZ', '131809.SZ', '131801.SZ',\
                     '131802.SZ', '131803.SZ', '131805.SZ', '131806.SZ',\
                     '204001.SH', '204002.SH', '204003.SH', '204004.SH', '204007.SH',\
                     '204014.SH', '204028.SH', '204091.SH', '204182.SH']  
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
    order = order[(order['date']==datetime.datetime.today().strftime("%Y%m%d"))&\
                    (~order['code'].isin(status_extract_codes))].copy()
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
    deal = deal[(deal['date']==datetime.datetime.today().strftime("%Y%m%d"))&\
                    (~deal['code'].isin(status_extract_codes))].copy()
    return deal[['id', 'order_id', 'code', 'date', 'deal_time',\
        'trade_type', 'price', 'vol', 'amount', 'remark']]

########################################### 买卖挂单 ###################################################

# 撤单 超过wait_dur s的订单取消
def cancel_order(C, wait_dur, stratname=None):
    order = get_order()
    # 全部可撤订单
    order = order[order['status'].map(lambda x:(x!=53)&(x!=54)&(x!=56)&(x!=57))].copy()
    # 属于该策略
    if stratname!=None:
        order = order[order['remark']==stratname].copy()
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
    if vol==0:
        print('too less vol to sub')
        return
    # 卖出，单标的，账号， 代码，限价单，价格，量，策略名，立即触发下单，备注
    if account_type=='STOCK':
        passorder(24, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(34, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
#买入
def buy(C, code, price, vol, strategyName=strategy_name, remark=strategy_name):
    vol = int((vol//multiples)*multiples)
    if vol==0:
        print('too less vol to sub')
        return
    if account_type=='STOCK':
        passorder(23, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单
    elif account_type=='CREDIT':
        passorder(33, 1101, ACCOUNT, code, 11, price, vol, strategyName, 2, remark, C) # 下单

########################################### 其他 ###################################################

# 存储全局变量
class a():
    pass



#######################################################################################################
#############################        策略主代码             ###########################################
#######################################################################################################


# 初始化准备
def prepare(C):
    strat_files = [f for f in os.listdir(stratfile_loc) \
                            if f.split('.')[-2].split('-')[-1]==stratfile_name]
    strat_files = sorted(strat_files)
    strat_file = stratfile_loc + strat_files[-1]
    df = pd.read_csv(strat_file, encoding='gbk')
    log('读取策略文件', strat_file)
    print('读取策略文件', strat_file)
    pos_init = get_pos()    # 初始持仓
    init_cap = pos_init['MarketValue']
    init_vol = pos_init['vol']
    sorted_codes = df['代码'].astype('str')+'.'+df['市场']           # 策略标的按打分排序
    holding_codes = set(init_cap.index)&set(sorted_codes[:holding_num].values)   # 排名holding_num之内的标的继续持有
    buy_codes = sorted_codes[~sorted_codes.isin(holding_codes)]                  # 如果继续持有标的不足buy_num只，则需要新买入，按打分排序填充
    buy_codes = buy_codes.values[:max(buy_num - len(holding_codes), 0)]
    target_codes = holding_codes|set(buy_codes)-set(extract_codes)               # 目标市值为 继续持有+新买入 标的等权*策略市值，去掉黑名单标的
    target_weights = pd.Series(1, index=list(target_codes))
    target_weights = target_weights/target_weights.sum()
    trade_codes = list((set(target_codes)|set(init_cap.index))-set(extract_codes))  # 交易涉及标的
    target_cap = (strat_cap*target_weights).reindex(trade_codes).fillna(0)
    log('目标市值')
    log(target_cap)
    init_cap = init_cap.reindex(trade_codes).fillna(0)
    init_vol = init_vol.reindex(trade_codes).fillna(0)   # 选中但非持仓转债持仓张数和市值为0
    log('初始持仓')
    log(pd.concat([init_vol, init_cap], axis=1))
    snapshot = get_snapshot(C, trade_codes)
    mid_snapshot = snapshot['mid']
    trade_cap = target_cap-init_cap
    trade_cap.loc[abs(trade_cap)<delta_min] = 0
    log('目标交易额小于最小变动阈值:'+','.join(list(trade_cap[trade_cap==0].index)))
    A.trade_vol = trade_cap/mid_snapshot
    A.sell_codes = list(set(target_cap[target_cap==0].index)\
                &set(init_vol[init_vol!=0].index))   # 清仓标的交易张数改为持仓
    A.trade_vol.loc[A.sell_codes] = -init_vol.loc[A.sell_codes]
    log('目标交易张数，市值，即时价格')     
    log(pd.concat([A.trade_vol, trade_cap, mid_snapshot], axis=1))
    A.traded_vol = pd.Series(0, A.trade_vol.index)   # 已成交张数
    A.remain_times = int(dur_time/interval)  # 剩余挂单轮数

# 挂单员
def trader(C):
    if A.remain_times==0:
        return
    log('第%s/%s轮挂单'%(int(dur_time/interval)-A.remain_times+1, int(dur_time/interval)))
    snapshot = get_snapshot(C, A.trade_vol.index)
    mid_snapshot = snapshot['mid']
    bidPrice_snapshot = snapshot['bidp1']
    askPrice_snapshot = snapshot['askp1']
    lastClose_snapshot = snapshot['lastClose']
    # 涨停不卖出、不排板
    limitup_codes = askPrice_snapshot[askPrice_snapshot.isna()|(askPrice_snapshot==0)]
    limitdown_codes = bidPrice_snapshot[bidPrice_snapshot.isna()|(bidPrice_snapshot==0)]
    should_trade_vol = (A.trade_vol - A.traded_vol).sort_values()  # 先卖再买
    for code, delta_vol in should_trade_vol.items():
        log('处理 %s %s'%(code, delta_vol))
        if code in limitup_codes.index:
            print('涨停不卖出，不排版')
            log('涨停不卖出，不排板')
            continue
        mean_vol = abs(delta_vol)/A.remain_times  # 平均每次需要交易张数绝对值
        price = mid_snapshot.loc[code]
        if (code not in A.sell_codes)&(abs(delta_vol*price)<delta_min):
            log('非清仓且与目标市值差距小于挂单金额，不交易')
            continue
        else:
            if mean_vol*price<delta_min:
                log('单笔成交金额小于最小值，已按最小值和需要成交张数低者挂单。')
                vol = min(delta_min/price, abs(delta_vol))
            elif mean_vol*price<delta_max:
                vol = mean_vol
            else:
                log('单笔成交金额超过最大值，已按最大值挂单。')
                vol = delta_max/price
        if delta_vol>0:
            # 跌停不买入
            if code in limitdown_codes.index:
                print('跌停不买入', code)
                log('跌停不买入', code)
            else:
                # 不能超过涨停价
                price = min(lastClose_snapshot[code]*(1+max_upndown), bidPrice_snapshot[code]*(tolerance+1))
                buy(C, code, price, vol)
                log('buy %s %s %s'%(code, price, vol))
                #print('buy', code, price, vol)
                A.traded_vol.loc[code] += int((vol//multiples)*multiples)
        else:
            price = min(lastClose_snapshot[code]*(1-max_upndown), askPrice_snapshot[code]*(1-tolerance))
            sell(C, code, price, vol)
            log('sell %s %s %s'%(code, price, vol))
            #print('sell', code, price, vol)
            A.traded_vol.loc[code] -= int((vol//multiples)*multiples)
    A.remain_times = A.remain_times-1

# 大概率不成交的单子进行撤单
def order_canceler(C):
    cancel_order(C, wait_dur, strategy_name)
    cancel_order_price(C, 0.01, strategy_name)

# 交易情况总结
def summary(C):
    log('总成交张数')                      # 已成交张数
    log(A.traded_vol)
    end_cap = get_pos()['MarketValue']     # 处理全部持仓
    log('结束时持仓')
    log(end_cap.loc[A.trade_vol.index].fillna(0))




# 初始化函数 主程序
def init(C):
    # 存储全局变量
    global A
    A = a()
    # 初始化时读取一次，之后每日8:30读取
    prepare(C)
    # 交易时间运行装饰器 交易日start到start+dur
    def trader_time(func):
        def wrapper(*args, **kwargs):
            today = datetime.datetime.now().date().strftime("%Y%m%d")
            now = datetime.datetime.now().time()
            if C.get_trading_dates('SH', today, today, 1, '1d'):
                if (datetime.time(int(start_time[:2]), int(start_time[2:4]), int(start_time[4:6])) \
                    <= now <= datetime.time(int(end_time[:2]), int(end_time[2:4]), int(end_time[4:6]))):
                    return func(*args, **kwargs)
                else:
                    pass
            else:
                pass
        return wrapper
   # 挂载定时函数
    global  f0, f1, f2, f3
    f0 = trader_time(order_canceler)   # 定时、按条件撤单程序
    C.run_time('f0', "1nSecond", "2022-08-01 09:15:00", "SH") # 每秒检查撤单
    C.run_time('prepare', "1d", "2022-08-01 %s:%s:%s"%(prepare_time[:2], prepare_time[2:4], prepare_time[4:6]),\
                    "SH") # 每天初始化函数
    # trader
    f1 = trader_time(trader)
    C.run_time('f1', "%snSecond"%interval, "2022-08-01 09:15:00", "SH") # 交易员
    C.run_time('summary', "1d", "2022-08-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], summary_time[4:6]),\
                    "SH") # 每天初始化函数
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT
