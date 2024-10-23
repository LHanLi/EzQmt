#######################################################################################################
########################################### 日常io运行 ###################################################
#######################################################################################################

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
        if type(message)==type(pd.Series()):
            for i,v in text.items():
                f.write(str(i)+','+str(v))
                f.write('\n')
        else:
            f.write("unable to identify message type\n")

#######################################################################################################
########################################### 行情数据 ###################################################
#######################################################################################################

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
    display_columns = ['code', 'lastPrice', 'amount', 'pvolume', 'high', 'low', 'open', 'lastClose',\
        'mid', 'askp1', 'askp2', 'askp3', 'askp4', 'askp5', \
            'bidp1', 'bidp2', 'bidp3', 'bidp4', 'bidp5', \
            'askv1', 'askv2', 'askv3', 'askv4', 'askv5',\
              'bidv1', 'bidv2', 'bidv3', 'bidv4', 'bidv5']
    df = df[display_columns].rename(columns={'volume':'vol'})
    df = df.set_index('code')
    # 有时，沪市转债单位是手，沪市需要乘一个沪市转化因子
    df['vol'] = df['vol']*df.index.map(lambda x: SHmul if 'SH' in x else SZmul if 'SZ' in x else 1)
    return df

#######################################################################################################
########################################### 账户状态 ###################################################
#######################################################################################################





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
    extract_names = ['新标准券', '国标准券', 'GC001', 'Ｒ-001']            # 逆回购仓位不看
    pos = pos[(pos['vol']!=0)&(~pos['name'].isin(extract_names))].copy()        # 已清仓不看
    return pos
# 获取账户状态 净值，现金
def get_account():
    acct_info = get_trade_detail_data(ACCOUNT, account_type, 'account')[0]
    return {'net':acct_info.m_dBalance, 'cash':acct_info.m_dAvailable}
# 获取订单状态 当日没有订单返回空表（但是有columns）
def get_order():
    order_info = get_trade_detail_data(ACCOUNT, account_type, 'ORDER')
    order_to_dict = lambda o:{
        'id':o.m_strOrderSysID,
        'code': o.m_strInstrumentID+'.'+o.m_strExchangeID,
        'sub_time': o.m_strInsertTime,          # 例如 str:095620
        'trade_type': o.m_nOffsetFlag,          # 48 买入/开仓；49 卖出/平仓
        'price': o.m_dLimitPrice,               # 挂单价
        'sub_vol': o.m_nVolumeTotalOriginal,
        'dealt_vol': o.m_nVolumeTraded,
        'remain_vol': o.m_nVolumeTotal,
        # 48 未报， 49 待报， 50 已报， 51 已报待撤，52 部成待撤， 53 部撤(部成撤单），
        # 54 已撤， 55 部成， 56 已成， 57 废单， 86 已确认， 255 未知
        'status':o.m_nOrderStatus,               
        'frozen':o.m_dFrozenMargin+o.m_dFrozenCommission,   # 冻结金额/保证金+手续费
    }
    order = pd.DataFrame(list(map(order_to_dict, order_info)))
    if order.empty:
        return pd.DataFrame(columns=['code', 'sub_time', 'trade_type', 'sub_vol', 'dealt_vol', \
                  'remain_vol', 'status'])
    order = order.set_index('id').sort_values('sub_time', ascending=False)
    return order[['code', 'sub_time', 'trade_type', 'sub_vol', 'dealt_vol', \
                  'remain_vol', 'status']]
# 成交情况
def get_dealt():
    order = get_order().reset_index()
    # 所有已撤、部成、已成订单
    dealt_total = order[order['status'].map(lambda x: x in [53, 54, 55, 56])].copy()
    # 买入\卖出
    bought_vol = dealt_total[dealt_total['trade_type']==48][['dealt_vol', 'code']].groupby('code').sum()
    sold_vol = -dealt_total[dealt_total['trade_type']==49][['dealt_vol', 'code']].groupby('code').sum()
    # 完成量
    dealt_vol = pd.concat([bought_vol['dealt_vol'], sold_vol['dealt_vol']])
    dealt_vol = dealt_vol[abs(dealt_vol).sort_values(ascending=False).index]
    return dealt_vol

#######################################################################################################
########################################### 买卖挂单 ###################################################
#######################################################################################################

#卖出 row包含订单信息
def sell(C, row):
    code = row['code'] # 标的代码
    price = row.target_price # 执行价格
    volume = row.m_nCanUseVolume # 执行数量
    strategyName = row.strategyName # 策略名
    remark = row.remark # 备注
    # 卖出，单标的，账号， 代码，限价单，价格，量，策略名，立即触发下单，备注
    passorder(24, 1101, ACCOUNT, code, 11, price, volume, strategyName, 2, remark, C) # 下单
#买入
def buy(C, row):
    code = row['code'] # 标的代码
    price = row.target_price # 执行价格
    volume = row.m_nCanUseVolume # 执行数量
    strategyName = row.strategyName # 策略名
    remark = row.remark # 备注
    # 卖出，单标的，账号， 代码，限价单，价格，量，策略名，立即触发下单，备注
    passorder(23, 1101, ACCOUNT, code, 11, price, volume, strategyName, 2, remark, C) # 下单
# 存储全局变量
class a():
    pass
