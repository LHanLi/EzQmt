# encoding:gbk
import datetime, re, os, time
import numpy as np
import pandas as pd

# 每交易日summary_time(16:20)输出账户当日市值/现金、持仓情况、交易结算情况、申报委托单等信息。

############### 请根据账户和本地配置修改以下部分 #####################
ACCOUNT = '**********'                                                   # 填写您的资金账号
account_type = 'STOCK'
strategy_name = 'summary'

logfile = 'D:/cloud/monitor/QMT/LogRunning/'                       # 填写您的日志文件保存位置   
logfile = logfile + ACCOUNT + '-' + strategy_name + '.txt' 
save_loc = 'D:/cloud/monitor/QMT/summary/'                         # 填写您的结算文件（本策略输出结果）保存位置
save_loc = save_loc + ACCOUNT + '/' + account_type + '/'    
summary_time = '162000'


#################################### 以下不可修改 ###################################

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

########################################### 其他 ###################################################

# 存储全局变量
class a():
    pass

##############################################################################################
###################################   策略   #################################################
##############################################################################################


def summary(C):
    today = datetime.datetime.now().date().strftime("%Y%m%d")
    # 如果有当日状态文件则删除
    def delete_file(file_path):
        # 检查文件是否存在
        if os.path.exists(file_path):
            os.remove(file_path)  # 删除文件
        else:
            pass
    summary_nams = {'acct':save_loc+'acct-'+today+'.csv',\
                        'pos':save_loc+'position-'+today+'.csv',\
                          'order':save_loc+'order-'+today+'.csv',\
                            'deal':save_loc+'deal-'+today+'.csv',\
                               'strat_pos':save_loc+'/stratpos-'+today+'.csv'}
    for f in summary_nams.keys():
        delete_file(summary_nams[f])
    # 账户
    acct = get_account()
    pd.Series(acct).to_csv(summary_nams['acct'])
    # 当日持仓记录 
    pos = get_pos()
    pos.to_csv(summary_nams['pos'], encoding='utf_8_sig')
    # 当日委托单
    order = get_order()
    order.to_csv(summary_nams['order'])
    # 当日成交
    deal = get_deal()
    deal.to_csv(summary_nams['deal'], index=False)
    log('summary success')


# 初始化函数 主程序
def init(C):
    #summary(C)
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
    global f
    f = trade_time(summary)
    C.run_time('f', "1d", "2024-01-01 %s:%s:%s"%(summary_time[:2], summary_time[2:4], \
        summary_time[4:6]), "SH") # 输出今日委托
    # 读取图形界面传入的ACCOUNT
    global ACCOUNT
    ACCOUNT = account if 'account' in globals() else ACCOUNT 
