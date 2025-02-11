import pandas as pd
import numpy as np
import FreeBack as FB
import os,datetime

class account():
    # 总结文件根目录，进出资金记录[('yyyy-mm-dd', 进出金额),..]，起止日期，业绩基准，转股信息（{转债代码：（股票代码，转股价）}，是否隐藏具体金额，策略合并
    def __init__(self, summary_loc, outcash_list=[], start_date=None, end_date=None, benchmark=None, conv_stk={}, if_hide=False, renamestrat={}, accnum=8888888888):
        self.summary_loc = summary_loc
        self.outcash_list = outcash_list
        net_file = sorted([f for f in os.listdir(self.summary_loc) if ('acct' in f)])
        if start_date==None:
            self.start_date = net_file[0].split('-')[1].split('.')[0]
        else:
            self.start_date = pd.to_datetime(start_date).strftime("%Y%m%d")
        if end_date==None:
            self.end_date = net_file[-1].split('-')[1].split('.')[0]
        else:
            self.end_date = pd.to_datetime(end_date).strftime("%Y%m%d")
        #if type(benchmark)==type(None):
        #    daterange = [pd.to_datetime(f.split('.')[0].split('-')[1]) for f in net_file]
        #    self.benchmark = pd.DataFrame({0:0}, index=daterange)
        #else:
        self.benchmark = benchmark
        self.conv_stk = conv_stk
        self.if_hide = if_hide
        self.renamestrat = renamestrat
        self.accnum = accnum
        self.get_acct()
        self.get_pos()
        self.get_deal()
        self.cal_stratpos()
        self.cal_contri()
    # net=现金+证券持仓（包括逆回购）
    def get_acct(self):
        net_file = sorted([f for f in os.listdir(self.summary_loc) if ('acct' in f) and \
                    (f.split('-')[1].split('.')[0]>=self.start_date) and (f.split('-')[1].split('.')[0]<=self.end_date) ])
        net = [] 
        for f in net_file:
            date = f[-12:-4]
            onedaynet = pd.read_csv(self.summary_loc+'/'+f, header=None).set_index(0).transpose()
            onedaynet['date'] = pd.to_datetime(date)
            net.append(onedaynet)
        net = pd.concat(net).set_index('date').sort_index()
        # 每日收益率 发生资金转入转出时需要对returns进行修正
        returns = (net['net']/net['net'].shift()-1).fillna(0)
        outcash = pd.Series({pd.to_datetime(i[0]):i[1] for i in self.outcash_list}, index=net.index).fillna(0)
        replace_returns = (net['net']/(net['net']+outcash.shift(-1)).shift()-1).loc[outcash!=0].loc[returns.index[0]:]
        returns.loc[replace_returns.index] = replace_returns
        net['returns'] = returns
        net.fillna(0)
        self.net = net
    # net=现金（包括逆回购）+证券持仓
    # 持仓按账号类型显示，而acct按账号全部持仓显示（包含股票、期权、港股通等），对于现金+逆回购之外部分记为unknown
    def get_pos(self):
        pos_file = sorted([f for f in os.listdir(self.summary_loc) if ('position' in f) and \
                            (f.split('-')[1].split('.')[0]>=self.start_date) and (f.split('-')[1].split('.')[0]<=self.end_date)])
        pos = []
        for f in pos_file:
            date = f[-12:-4]
            onedaypos = pd.read_csv(self.summary_loc+'/'+f)
            onedaypos['date'] = pd.to_datetime(date)
            pos.append(onedaypos)
        pos = pd.concat(pos).set_index(['date', 'code'])
        yichang = pos[~(pos['MarketValue']<999999)].index  # 新债申购持仓
        pos.loc[yichang, 'MarketValue']  = pos.loc[yichang, 'PositionCost']
        # 普通持仓的价格代表收盘价，逆回购代表利率
        pos['price'] = pos['MarketValue']/pos['vol']
        # 修正逆回购持仓MarketValue，并且添加至net中新增一列为total_cash
        self.nihuigou_codes = ['131810.SZ', '131811.SZ', '131800.SZ', '131809.SZ', '131801.SZ',\
                            '131802.SZ', '131803.SZ', '131805.SZ', '131806.SZ',\
                            '204001.SH', '204002.SH', '204003.SH', '204004.SH', '204007.SH',\
                            '204014.SH', '204028.SH', '204091.SH', '204182.SH']   # 深市、沪市逆回购代码
        nihuigou = pos[pos.index.get_level_values(1).isin(self.nihuigou_codes)].copy()
        nihuigou['MarketValue'] = nihuigou['vol']*100
        nihuigou['name'] = '逆回购'
        paichunihuigou = pos[~pos.index.get_level_values(1).isin(self.nihuigou_codes)].copy()
        pos = pd.concat([nihuigou, paichunihuigou]).sort_index()
        # 如果总资产-现金-持仓 大于1，则表明有未知持仓（例如港股通）
        unknown_value = self.net['net']-self.net['cash']-pos['MarketValue'].groupby('date').sum()
        if unknown_value.max()>1:
            unknown_value = unknown_value.reset_index().rename(columns={0:'MarketValue'})
            unknown_value['code'] = 'unknown'
            pos = pd.concat([pos, unknown_value.set_index(['date', 'code'])]).sort_index()
        pos.loc[pos.index.get_level_values(1)=='unknown', 'PositionCost'] = 0 
        pos.loc[pos.index.get_level_values(1)=='unknown', 'name'] = '港股通等持仓'
        pos.loc[pos.index.get_level_values(1)=='unknown', 'price'] = 1
        pos.loc[pos.index.get_level_values(1)=='unknown', 'vol'] =  \
                    pos.loc[pos.index.get_level_values(1)=='unknown', 'MarketValue']
        pos.loc[pos.index.get_level_values(1)=='unknown', 'AvailableVol'] = \
            pos.loc[pos.index.get_level_values(1)=='unknown', 'vol']
        pos = pos[pos['vol']>1].copy()
        # 将逆回购计为现金，添加总现金字段
        self.net['total_cash'] = self.net['cash'].add(\
                pos[pos['name']=='逆回购'].groupby('date')['MarketValue'].sum(), fill_value=0)
        self.pos = pos
        self.code2name = dict(zip(self.pos.index.get_level_values(1), self.pos['name']))
    # 成交数据
    def get_deal(self):
        deal_file = sorted([f for f in os.listdir(self.summary_loc) if ('deal' in f) and \
                            (f.split('-')[1].split('.')[0]>=self.start_date) and (f.split('-')[1].split('.')[0]<=self.end_date)])
        deal = [] 
        for f in deal_file:
            date = f[-12:-4]
            onedaydeal = pd.read_csv(self.summary_loc+'/'+'deal-%s.csv'%date)
            deal.append(onedaydeal)
        deal = pd.concat(deal)
        # 以时间戳为唯一index
        deal['date'] = deal.apply(lambda x: pd.to_datetime(str(x['date'])+\
                '%06d'%x['deal_time']), axis=1)
        deal = deal.rename(columns={'remark':'strat'})
        deal['strat'] = deal['strat'].fillna('craft')
        deal = deal.sort_values(by='date').reset_index()[['date', 'code', 'trade_type', 'price', 'vol', 'amount', 'strat']].sort_values(by='date').copy()
        deal['vol'] = deal['vol']*pd.Series(np.where(deal['trade_type']==48, 1, -1), deal.index)
        deal['amount'] = deal['amount']*pd.Series(np.where(deal['trade_type']==49, 1, -1), deal.index)  # 48为买入，49为卖出。
        deal['time'] = deal['date'] + deal.index.map(lambda x: datetime.timedelta(microseconds=x%100))  # 避免时间戳重复
        deal = deal.set_index('time').sort_index()
        deal['date'] = deal.index.map(lambda x :pd.to_datetime(x.date()))
        deal.loc[deal['strat'].isna(), 'strat'] = 'craft'  # 未备注标记为craft
        # 将转股委托变为成交订单   次日9：15卖出转债，买入股票
        #if self.conv_stk != {}:
        order_file = sorted([f for f in os.listdir(self.summary_loc) if ('order' in f) and \
                                (f.split('-')[1].split('.')[0]>=self.start_date) and (f.split('-')[1].split('.')[0]<=self.end_date)])
        order = []
        for f in order_file:
            date = f[-12:-4]
            onedayorder = pd.read_csv(self.summary_loc+'/'+'order-%s.csv'%date)
            order.append(onedayorder)
        order = pd.concat(order)
        # 48 未报， 49 待报， 50 已报， 51 已报待撤， 52 部成待撤， 53 部撤（剩余已撤单）， 54 已撤， 55 部成， 56 已成， 57 废单， 227 未知
        conv_order = order[(order['price']==0)&(order['status']==50)].rename(columns={'remark':'strat'})
        if not conv_order.empty:
            print(conv_order)
            conv_order['strat'] = 'craft'
            conv_order['price'] = conv_order.apply(lambda x: self.pos.loc[str(x['date']), x['code']]['price'], axis=1) # 收盘价结算
            conv_order['vol'] = conv_order['sub_vol']
            stk_vol = conv_order['vol']*(100/conv_order['code'].map(lambda x: self.conv_stk[x][1])) 
            amount = conv_order['price']*conv_order['vol'] 
            conv_order['amount'] = amount
            conv_order['date'] = conv_order['date'].map(lambda x: \
                    self.net.index[np.searchsorted(self.net.index, pd.to_datetime(str(x)), 'left')+1])  # 规定转股在T+1日9：15发生
            conv_order['time'] = conv_order['date']+datetime.timedelta(hours=9, minutes=15)  
            conv_order = conv_order[['time', 'date', 'code', 'trade_type', 'price', 'vol', 'amount', 'strat']]
            # 转股委托转化为卖出转债同时买入正股的成交订单
            conv_order_sell = conv_order.copy()
            conv_order_sell['vol'] = -conv_order_sell['vol']
            conv_order_buy = conv_order.copy() 
            conv_order_buy['trade_type'] = 48
            conv_order_buy['vol'] = stk_vol.astype('int') 
            conv_order_buy['amount'] =  conv_order['code'].map(lambda x: self.conv_stk[x][1])*(stk_vol-stk_vol.astype('int'))\
                                             - amount # 小数股直接转为现金
            conv_order_buy['price'] = -conv_order_buy['amount']/conv_order_buy['vol']
            conv_order_buy['code'] = conv_order_buy['code'].map(lambda x: self.conv_stk[x][0])
            self.conv_deal = pd.concat([conv_order_sell, conv_order_buy]).set_index('time')
            deal = pd.concat([deal, self.conv_deal])
        # 逆回购持仓转化为成交订单
        # 申购转为当日15:30现金换券，次日8:00券换现金
        nihuigou_pos = self.pos[self.pos['name']=='逆回购'].reset_index()
        nihuigou_pos['strat'] = '逆回购'
        nihuigou_pos['trade_type'] = 48
        nihuigou_pos['amount'] = -nihuigou_pos['MarketValue']
        nihuigou_pos = nihuigou_pos[['date', 'code', 'trade_type', 'price', 'vol', 'amount', 'strat']]
        nihuigou_buy = nihuigou_pos.copy()
        nihuigou_buy['time'] = nihuigou_buy['date'] + datetime.timedelta(hours=15, minutes=30)
        nihuigou_sell = nihuigou_pos[nihuigou_pos['date']<self.net.index[-1]].copy()  # 如果是最后一天则不添加卖出逆回购订单
        nihuigou_sell['trade_type'] = 49
        nihuigou_sell['vol'] = -nihuigou_sell['vol']
        nihuigou_sell['amount'] = -nihuigou_sell['amount']*(1+nihuigou_sell['price']/100/365)
        nihuigou_sell['date'] =  nihuigou_sell['date'].map(lambda x: \
                np.nan if np.searchsorted(self.net.index, x, 'left')+1>=len(self.net.index) \
                    else self.net.index[np.searchsorted(self.net.index, x, 'left')+1]) 
        nihuigou_sell = nihuigou_sell.dropna(subset=['date'])
        nihuigou_sell['time'] = nihuigou_sell['date'] + datetime.timedelta(hours=8)  # T+1日8:00,逆回购变为现金
        self.nihuigou_deal = pd.concat([nihuigou_buy.set_index('time'), nihuigou_sell.set_index('time')])
        deal = pd.concat([deal, self.nihuigou_deal])
        # 账户总资产和订单结算结果差异转化为申购新股新债或账号外持仓
        # 申购（**发债）转为当日16:00买入，代码转变（**发债改为**）当日9:00卖出
        unstackpos = self.pos['vol'].unstack().fillna(0)
        deltapos  = (unstackpos-unstackpos.shift()).stack()
        deltapos = deltapos[deltapos!=0].copy()   # 持仓变化
        net_deal = deal.groupby(['date', 'code'])['vol'].sum()
        net_deal = net_deal.loc[deltapos.index[0][0]:]
        net_deal = net_deal[net_deal!=0].copy()  # 成交
        subscrible_deal = deltapos.sub(net_deal, fill_value=0)
        subscrible_deal = subscrible_deal[subscrible_deal!=0]
        subscrible_deal = subscrible_deal.reset_index().rename(columns={0:'vol'})
        if not subscrible_deal.empty:
            if (set(subscrible_deal['code'])-set(['unknown']))!=set():
                print('当前交割记录和持仓不匹配标的：', set(subscrible_deal['code'])-set(['unknown']), \
                  '按申购新股/新债处理')
            try:
                subscrible_deal['price'] = subscrible_deal['code'].map(lambda x: self.pos.loc[:, x, :]['price'].iloc[0])
            except:
                print('请检查可转债转股信息是否添加', subscrible_deal['code'].unique())
                return 
            subscrible_deal['trade_type'] = subscrible_deal['vol'].map(lambda x: 48 if x>0 else 49)
            subscrible_deal['time'] = subscrible_deal['date'].map(lambda x: x + datetime.timedelta(hours=9))
            subscrible_deal['amount'] = -subscrible_deal['vol']*subscrible_deal['price']
            subscrible_deal['time'] = subscrible_deal['date'] + \
                    subscrible_deal['vol'].map(lambda x: datetime.timedelta(hours=16 if x>0 else 9))
            subscrible_deal['strat'] = 'craft'
            self.subscrible_deal = subscrible_deal.set_index('time')        
            # 主账号外持仓，如果有的话需要
            out_deal = self.subscrible_deal[self.subscrible_deal['code']=='unknown'].copy()
            if not out_deal.empty:
                print('存在Stock账号外持仓（港股通等）')
                self.subscrible_deal = self.subscrible_deal[self.subscrible_deal['code']!='unknown'].copy()
                out_deal['strat'] = '港股通等持仓'
                if self.net.index[0] in self.pos[self.pos['name']=='港股通等持仓'].index.get_level_values(0):
                    init_out_deal = self.pos[self.pos['name']=='港股通等持仓'].loc[[self.net.index[0]], :].reset_index()
                    init_out_deal['time'] = init_out_deal['date']+datetime.timedelta(hours=16)
                    init_out_deal['trade_type'] = 48
                    init_out_deal['amount'] = -init_out_deal['MarketValue']
                    init_out_deal['strat'] = '港股通等持仓'
                    init_out_deal = init_out_deal.set_index('time')\
                        [['date', 'code', 'trade_type', 'price', 'vol', 'amount', 'strat']]
                    self.out_deal = pd.concat([init_out_deal, out_deal])
                deal = pd.concat([deal, self.out_deal])
            # 全部订单
            deal = pd.concat([deal, self.subscrible_deal])
        self.deal = deal.sort_index()
        # 策略改名
        self.deal['strat'] = self.deal['strat'].map(lambda x: \
                x if x not in self.renamestrat.keys() else self.renamestrat[x]) 
        self.strats = list(self.deal['strat'].unique())   # 运行中策略
        print('当前运行中策略：%s'%(','.join(self.strats)))
    # 订单数据（包含转股信息）
    def get_order(self):
        pass 
    def cal_stratpos(self):
        stratpos = []
        for date in self.net.index:
            # 当日成交 
            deal = self.deal[self.deal['date']==date].copy()
            # 首日持仓
            if date==self.net.index[0]:
                todaystratpos = self.pos.loc[date]['vol']
                net_deal = deal.groupby('code')['vol'].sum()
                sell_deal = deal[deal['vol']<0].groupby('code')['vol'].sum()
                buy_deal = deal[deal['vol']>0].groupby(['strat', 'code'])['vol'].sum()
                # 推测前日持仓
                prestratpos = todaystratpos.add(-net_deal, fill_value=0)
                prestratpos = prestratpos[prestratpos!=0].copy()
                # 当日先卖出后持仓全为craft
                todaystratpos0 = prestratpos.add(sell_deal, fill_value=0)
                todaystratpos0 = todaystratpos0.reset_index()
                todaystratpos0['strat'] = 'craft'
                todaystratpos0 = todaystratpos0.set_index(['strat', 'code'])['vol']
                todaystratpos0 = todaystratpos0[todaystratpos0!=0].copy()
                # 首日策略持仓
                todaystratpos = todaystratpos0.add(buy_deal, fill_value=0)
            else:
                prestratpos = pd.read_csv(self.summary_loc+'/stratpos-'+\
                    self.net.index[np.searchsorted(self.net.index, date, side='left')-1].strftime("%Y%m%d")+'.csv').\
                        set_index(['strat', 'code'])['vol']
                net_deal = deal.groupby(['strat', 'code'])['vol'].sum()
                todaystratpos = prestratpos.add(net_deal, fill_value=0)
            # 如果有策略的某标的持仓为负，
            negpos = todaystratpos[todaystratpos<0].copy()
            while not negpos.empty:
                #print('%s,策略持仓为负:'%date)
                #print(negpos)
                todaystratpos = todaystratpos[todaystratpos>0].copy()
                # 归为持仓该标的数量最多的策略
                code2strat = todaystratpos.sort_values(ascending=False).reset_index().drop_duplicates(subset=['code'])
                code2strat = dict(zip(code2strat['code'], code2strat['strat']))
                # 忽略负持仓所属策略
                negpos = negpos.groupby('code').sum().reset_index()
                negpos['strat'] = negpos['code'].map(lambda x: 'craft' if x not in code2strat.keys() else code2strat[x])
                #print('该部分持仓归为:')
                #print(todaystratpos)
                todaystratpos = todaystratpos.add(negpos.set_index(['strat', 'code'])['vol'], fill_value=0)
                negpos = todaystratpos[todaystratpos<0].copy()
            todaystratpos = todaystratpos[todaystratpos!=0]
            todaystratpos.to_csv(self.summary_loc+'/stratpos-'+date.strftime("%Y%m%d")+'.csv')
            todaystratpos = todaystratpos.reset_index()
            todaystratpos['date'] = date
            todaystratpos = todaystratpos.set_index(['date', 'strat', 'code'])
            stratpos.append(todaystratpos)
        stratpos = pd.concat(stratpos)
        # 修正pos，逆回购价格改为100
        correctpos = self.pos.copy()
        correctpos['price'] = correctpos.apply(lambda x: 100 if x['name']=='逆回购' else x['price'], axis=1)
        stratpos = stratpos.reset_index().merge(correctpos.reset_index()[['code', 'date', 'price', 'name']], on=['date', 'code'])
        stratpos['MarketValue'] = stratpos['price']*stratpos['vol']
        self.stratpos = stratpos.set_index(['date', 'strat', 'code'])
        # 策略持仓/成交分仓
        self.split_strats = {} 
        for strat in self.strats:
            try:
                self.split_strats[strat] = (self.stratpos.loc[:, strat, :], self.deal[self.deal['strat']==strat])
            except:
                self.split_strats[strat] = (self.stratpos.loc[[]], self.deal[self.deal['strat']==strat])
    # 获取所有策略按持仓归因收益
    def cal_contri(self):
        self.df_contri = {}
        self.contri = {}
        for strat in self.strats+['all']: 
            if strat=='all':
                pos_ = self.pos
                deal_ = self.deal[self.deal['strat']!='港股通等持仓']  # 计算收益时忽略港股通等持仓订单
            else:
                pos_ = self.split_strats[strat][0]
                #if strat=='港股通等持仓':
                #   deal_ = self.deal[[]]
                #else:
                deal_ = self.split_strats[strat][1]
            all_tradedates = list(pos_.index.get_level_values(0))+list(deal_['date'].values)
            # T日相对T-1日策略持仓市值变动
            if not pos_.empty:     # 有策略始终无隔夜持仓
                pos_unstack = pos_[['vol', 'MarketValue']].unstack().fillna(0).\
                    reindex(self.net.index).loc[min(all_tradedates):max(all_tradedates)].fillna(0)
                pos_unstack = (pos_unstack-pos_unstack.shift().fillna(0))
                pos_delta = pos_unstack['MarketValue']
                pos_delta_vol = pos_unstack['vol']
            # T日交易净流水
            deal_ = deal_.groupby(['date', 'code'])[['vol', 'amount']].sum().unstack().fillna(0)
            deal_net = deal_['amount']
            deal_net_vol = deal_['vol']
            # T日交易净张数和持仓变化不相等的部分是策略订单操作了不属于自己策略的持仓造成的，需将此部分划转造成的资金变动归还
            # 负值表示该策略卖出了其他策略持仓，正值表示其他策略卖出了该策略持仓
            if not pos_.empty:
                lost = deal_net_vol.sub(pos_delta_vol, fill_value=0)
            else:
                lost = deal_net_vol
            lost = lost.stack()[lost.stack()!=0]   
            amountlend2others = (lost*self.pos['price'].unstack().shift().stack()).dropna() # 对于前日有持仓标的按照前收价其他策略划转市值，按前收计价
            VWAP = self.deal.copy()
            VWAP['vol'] = abs(VWAP['vol'])
            VWAP['amount'] = abs(VWAP['amount'])
            VWAP = VWAP.groupby(['date', 'code'])[['vol', 'amount']].sum()
            VWAP = VWAP['amount']/VWAP['vol']
            amountlend2othersT0 = lost.drop(amountlend2others.index)   
            amountlend2othersT0 = (amountlend2othersT0*VWAP).dropna()  # 前日策略无持仓标的按照成交均价计价
            deal_otherstrats = pd.concat([amountlend2others, amountlend2othersT0]).sort_index()
            deal_otherstrats = deal_otherstrats.unstack().fillna(0)
            if 'unknown' in deal_otherstrats.columns:
                deal_otherstrats.loc[:, 'unknown'] = 0
            # 收益分解
            if strat=='港股通等持仓':
                contri_strat = pos_delta.fillna(0)
            elif not pos_.empty:
                contri_strat = pos_delta.add(deal_net, fill_value=0).fillna(0).add(deal_otherstrats, fill_value=0)
            else:
                contri_strat = deal_net.fillna(0).add(deal_otherstrats, fill_value=0)
            if self.net.index[0] in contri_strat.index:
                contri_strat.loc[self.net.index[0], :] = 0  # 如果策略从开始日期开始则设置当天策略盈亏为0
            self.df_contri[strat] = contri_strat
            # 标的总盈亏
            pnl_total = contri_strat.sum()
            pnl_total.name = '总盈亏'
            # 简称/平均仓位/持仓金额
            #pos_name = pd.Series(dict(zip(pos_.index.get_level_values(1), pos_.values)))
            pos_name = pd.Series(pnl_total.index.map(lambda x: np.nan if x not in self.code2name.keys() else self.code2name[x]), index=pnl_total.index)
            pos_name.name = '标的简称'
            pos_ratio = 100*(pos_['MarketValue']/pos_['MarketValue'].groupby('date').sum()).groupby('code').mean()
            pos_ratio.name = '平均仓位(%)'
            pos_amount = pos_['MarketValue'].groupby('code').mean()
            pos_amount.name = '平均持仓金额(元)'
            self.contri[strat] = pd.concat([pos_name, pos_amount, pos_ratio, pnl_total], axis=1).sort_values(by='总盈亏') 
    # 计算交易滑点（按照开盘价/收盘价/开盘收盘平均价/VWAP四种基准），需提供分钟线数据。
    def cal_deal_comm(self, min_data, deal0):
        deal0['date'] = deal0['date'] + deal0.index.map(lambda x: \
                datetime.timedelta(hours=15, minutes=0) if ((x.hour==15)&(x.minute==0))|((x.hour==14)&(x.minute==59)) \
                    else datetime.timedelta(hours=x.hour, minutes=x.minute+1))
        deal0 = deal0.set_index(['date', 'code'])
        # 正为买入，负为卖出
        bought_deal = deal0[deal0['trade_type']==48].copy()
        sold_deal = deal0[deal0['trade_type']==49].copy()
        bought_vol = bought_deal.groupby(['date', 'code'])['vol'].sum()
        bought_vol.name = 'myvol'
        bought_amount = -bought_deal.groupby(['date', 'code'])['amount'].sum()
        bought_amount.name = 'myamount'
        bought = pd.concat([bought_vol, bought_amount], axis=1)
        bought['type'] = 'buy'
        bought['price'] = bought['myamount']/bought['myvol']
        bought = bought.join(min_data).dropna()
        sold_vol = -sold_deal.groupby(['date', 'code'])['vol'].sum()
        sold_vol.name = 'myvol'
        sold_amount = sold_deal.groupby(['date', 'code'])['amount'].sum()
        sold_amount.name = 'myamount'
        sold = pd.concat([sold_vol, sold_amount], axis=1)
        sold['type'] = 'sell'
        sold['price'] = sold['myamount']/sold['myvol']
        sold = sold.join(min_data).dropna()
        # 滑点
        bought['comm_close'] = 1e4*(bought['price']-bought['close'])/bought['close']
        sold['comm_close'] = 1e4*(sold['close']-sold['price'])/sold['close']
        bought['comm_open'] = 1e4*(bought['price']-bought['open'])/bought['open']
        sold['comm_open'] = 1e4*(sold['open']-sold['price'])/sold['open']
        # open close 平均价
        bought['comm_mco'] = 1e4*(bought['price']-(bought['close']+bought['open'])/2)/((bought['close']+bought['open'])/2)
        sold['comm_mco'] = 1e4*((sold['close']+sold['open'])/2-sold['price'])/((sold['close']+sold['open'])/2)
        bought['comm_avg'] = 1e4*(bought['price']-bought['avg'])/bought['avg']
        sold['comm_avg'] = 1e4*(sold['avg']-sold['price'])/sold['avg']
        deal_comm = pd.concat([bought, sold]).sort_index()
        return deal_comm
    # 净值  default 默认值， None 0基准
    def pnl(self, strat='all', benchmark='default'):
        start_date = self.df_contri[strat].index[0]
        end_date = self.df_contri[strat].index[-1]
        if type(benchmark)==str:
            if benchmark=='default':
                benchmark = self.benchmark
        if strat=='all':
            equity = self.net['net']
            plot_returns = self.net['returns']
        else:
            equity = self.split_strats[strat][0].groupby('date')['MarketValue'].sum().\
                        reindex(self.df_contri[strat].index).ffill()
            plot_returns = self.df_contri[strat].sum(axis=1)/equity

        self.post0 = FB.post.ReturnsPost(plot_returns, benchmark)
        plt, fig, ax = FB.display.matplot()
        lb = []
        # 策略走势
        l, = ax.plot((plot_returns+1).cumprod(), c='C3', linewidth=2)
        lb.append(l)
        # 如果基准是0就不绘制了
        if not type(benchmark)==type(None):
            # 基准走势
            colors = ['C0', 'C1', 'C2', 'C4', 'C5', 'C6', 'C7', 'C8']
            for i in range(len(benchmark.columns)):
                benchmark_returns = benchmark.iloc[:, i].loc[self.net.index[0]:self.net.index[-1]]
                l, = ax.plot((benchmark_returns+1).cumprod(), colors[i])
                lb.append(l)
        # 策略净资产
        ax2 = ax.twinx()
        l, = ax2.plot(equity/1e4, c='C3', alpha=0.5, ls='--')
        lb.append(l)
        plt.legend(lb, [('组合' if strat=='all' else '策略') + '收益',]+ \
                   ([] if type(benchmark)==type(None) else list(benchmark.columns))+\
                    [('组合总' if strat=='all' else '策略') +  '资产（右）'] , bbox_to_anchor=(0.9, -0.2), ncol=3)
        ax.set_title('资金账号：%s****%s'%(str(self.accnum)[:4], str(self.accnum)[-4:]) if strat=='all' else\
                        '策略：%s'%strat)
        ax2.set_ylabel('(万元)')
        if self.if_hide:
            ax2.set_yticks(ax2.get_yticks(), ['*.*' for i in ax2.get_yticks()])
        ax.set_ylabel('净值走势')
        ax.set_xlim(start_date, end_date)
        if strat=='all':
            ax.text(0, -0.25, '1、右轴为组合总资产', fontsize=10, transform=ax.transAxes)
        else:
            ax.text(0, -0.25, '1、右轴为策略总资产\n2、无隔夜持仓策略总资产为0', fontsize=10, transform=ax.transAxes)
        plt.gcf().autofmt_xdate()
        FB.post.check_output()
        plt.savefig('output/%s.png'%self.accnum, bbox_inches='tight')
        plt.show()
    # 月度收益
    def pnl_monthly(self, strat='all'):
        if strat=='all':
            plot_returns = self.net['returns']
        else:
            equity = self.split_strats[strat][0].groupby('date')['MarketValue'].sum().\
                        reindex(self.df_contri[strat].index).ffill()
            plot_returns = self.df_contri[strat].sum(axis=1)/equity
        self.post0 = FB.post.ReturnsPost(plot_returns, self.benchmark, show=False)
        self.post0.pnl_monthly()
    # 多策略仓位
    def displaystrats_pos(self, ratio=True):
        split_strats_pos = {}
        for strat in self.split_strats.keys():
            split_strats_pos[strat] = self.split_strats[strat][0].groupby('date')['MarketValue'].sum()
        split_strats_pos = pd.DataFrame(split_strats_pos).fillna(0)
        split_strats_pos['现金'] = self.net['cash']

        plt, fig, ax = FB.display.matplot()
        if ratio:
            split_strats_pos = 100*split_strats_pos.div(split_strats_pos.sum(axis=1), axis=0)
            #split_strats_pos = split_strats_pos.drop(columns='现金')
        ax.stackplot(split_strats_pos.index, split_strats_pos.values.T, \
                        labels=split_strats_pos.columns, alpha=0.8)
        if (~ratio) & self.if_hide:
            ax.set_yticks(ax.get_yticks(), ['*.*' for i in ax.get_yticks()])
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3)
        if ratio:
            ax.set_title('各策略及现金仓位')
            ax.set_ylabel('（%）')
        else:
            ax.set_title('各策略及现金市值')
            ax.set_ylabel('（元）')
        FB.post.check_output()
        plt.savefig('output/%s_strats_pos.png'%self.accnum, bbox_inches='tight')
        plt.show()
    # 多策略盈亏
    def displaystrats_pnl(self, ratio=True):
        plt, fig, ax = FB.display.matplot()
        df_net = []
        for stratname in self.strats:
            if ratio:
                net = (1+self.df_contri[stratname].sum(axis=1)/\
                    self.split_strats[stratname][0].groupby('date')['MarketValue'].sum().\
                        reindex(self.df_contri[stratname].index).ffill()).cumprod()
            else:
                net = self.df_contri[stratname].sum(axis=1).cumsum()
            net.name = stratname
            df_net.append(net)
        df_net = pd.concat(df_net, axis=1) 
        for stratname in df_net.columns:
            ax.plot(df_net[stratname].dropna(), label=stratname)
        if ratio:
            ax.set_ylabel('策略归一化净值')
        else:
            ax.set_ylabel('（元）')
        if (~ratio) & self.if_hide:
            ax.set_yticks(ax.get_yticks(), ['*.*' for i in ax.get_yticks()])
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3)
        FB.post.check_output()
        plt.savefig('output/%s_strats_pnl.png'%self.accnum, bbox_inches='tight')
        plt.show()
