## Importing packages ## 导入相关模块，顺序有所调整
from collections import Counter
import datetime as dt
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from importlib import reload
import itertools
from itertools import combinations as combo_func
import json
import math
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from pandas.tseries.offsets import WeekOfMonth
import pickle
import plotly.graph_objects as go
import requests
import scipy
import statistics
import time

###########################################################################################
##
## plt中文显示不乱码
plt.rcParams['font.sans-serif']=['SimHei']
plt.rcParams['axes.unicode_minus'] = False

pd.set_option('display.max_colwidth', 400)
pd.set_option('display.max_columns', 50)
pd.set_option('display.max_rows', 20)

# class TransactionLedgerIntegration:
# class TransactionLedgerMapping:

class TransactionJEM:
    def __init__(self, df, XR0_df, XR1_df, fillempty=''):
        """
            🚀 include variables for exchange rates?
            🚀 use iterrows? for i,row in df.iterrows(): i becomes dfi row becomes dfrow
            🚀 review if, elif logic of the selling FAE function, can use HM's code as a reference
            ⚠️ must import avg book price of each security for when calculating g/l during sell-out
            ⚠️ using average cost method to account for average book price per share; LIFO/FIFO too complex at this stage
            ⚠️ edit open FAE function to include IS changes (avgbp, unitsheld)
        """
        ## df implies the dataframe of transactions, hence 'TransactionLedgerMapping'
        self.df = df
        self.je_cols = self.df[[col for col in self.df.columns if col.startswith('DR') or col.startswith('CR')]] ## journal entry columns
        self.fillempty = fillempty ## empty string '' or None
        self.XR0_df = XR0_df
        self.XR1_df = XR1_df
        
    def concat_je_rows(*je_rows): ## variable-length arguments, *args 
        """
        Use as: 
            df_combined = concat_je_rows(df1, df2, df3, df4, ...)
                or
            df_list = [df1, df2, df3]
            df_combined = concat_je_rows(*df_list)
        """
        merged_debits_credits = pd.concat(je_rows, axis=0, sort=False)
        value_cols = [col for col in merged_debits_credits.columns if 'value' in col]
        merged_debits_credits[value_cols] = merged_debits_credits[value_cols].applymap(
            lambda x: float(f"{x:.2f}") if isinstance(x, (int, float)) else x
        )
        merged_debits_credits = merged_debits_credits.fillna(self.fillempty)
        transaction_df = pd.concat([self.df, merged_debits_credits], axis=1)
        return transaction_df
    
    def func_div_cash_rcvd(self, idx): ## dividend cash received ## 股息现金存入
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0'],
                                data=[[f'SCF_OA_DRC_{trxn_curr}', trxn_val, f'SCI_I_DI_{trxn_curr}', trxn_val]],
                                )
        return je_dfrow
        
    def func_int_cash_rcvd(self, idx): ## interest cash received ## 利息现金存入
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0'],
                                data=[[f'SCF_OA_IRC_{trxn_curr}', trxn_val, f'SCI_I_II_{trxn_curr}', trxn_val]],
                                )
        return je_dfrow

    def func_FAE_open(self, idx): ## open financial asset equity ## 建仓金融资产权益
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', trxn_val, 
                                       f'SCF_OA_PPI_{trxn_curr}_{sec_code}',trxn_val]]
                                )
        return je_dfrow      

    def func_FAE_close(self, idx, exp, ae, exe, cs, cp, 
                        avgbp_t0, unitsheld_t0, SFP_A_FA_O_curr_CUM_UGLΔFV_t0, 
                        underlying_sec_code): ## close financial asset equity ## 平仓金融资产权益
        ## avgbp_t0 = average book price (per share) from last period; this is also specific to the exact security
        ## unitsheld_t0 = number of units of security (shares) held on the books in the last period; this is also specific to the exact security
        ## SFP_A_FA_E_curr_CUM_UGLΔFV_t0 = cumulative unrealized gain or loss at fair value from last period (this is an adjunct asset account); this is also specific to the exact security
        ### we need to close this account out by the pro rata portion; positive value implies a DR balance and negative value implies a CR balance
        ## the 3 inputs avgbp_t0, unitsheld_t0, SFP_A_FA_E_curr_CUM_UGLΔFV_t0 must be sourced from the previous period's Investment Schedule

        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        trxn_quan = transaction['Trxn_quantity']
        
        ugl_t0 = 0 ## unrealized g/l for period t0 (last period); 1 for gain DR, -1 for loss CR, 0 for breakeven
        if SFP_A_FA_E_curr_CUM_UGLΔFV_t0 > 0:
            ugl_t0 = 1 
        elif SFP_A_FA_E_curr_CUM_UGLΔFV_t0 < 0:
            ugl_t0 = -1

        rgl_t1 = 0 ## realized g/l for period t1 (current period); 1 for gain, -1 for loss, 0 for breakeven
        if trxn_val > (trxn_quan * avgbp_t0):
            rgl_t1 = 1 ## realized a gain upon closing this position
        elif trxn_val < (trxn_quan * avgbp_t0):
            rgl_t1 = -1 ## realized a loss upon closing this position
        ################
        ################
        ## first we need to close out the unrealized gain/loss account; this is a pro rata portion of the cumulative unrealized gain/loss account
        if ugl_t0 == 1: ## implies a DR balance, so we must have SFP_A_FA_E_curr_CUM_UGLΔFV on CR to close out the DR balance
            je_dfrow_0 = pd.DataFrame(  index=[idx],
                                        columns=['DR_account_0', 'DR_value_0', 
                                                'CR_account_0', 'CR_value_0'],
                                        data=[[f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', (trxn_quan / unitsheld_t0) * SFP_A_FA_E_curr_CUM_UGLΔFV_t0,
                                            f'SFP_A_FA_E_{trxn_curr}_CUM_UGLΔFV_{sec_code}', (trxn_quan / unitsheld_t0) * SFP_A_FA_E_curr_CUM_UGLΔFV_t0]]
                                      )

        elif ugl_t0 == -1: ## implies a CR balance, so we must have SFP_A_FA_E_curr_CUM_UGLΔFV on DR to close out the CR balance
            je_dfrow_0 = pd.DataFrame(  index=[idx],
                                        columns=['DR_account_0', 'DR_value_0', 
                                                'CR_account_0', 'CR_value_0'],
                                        data=[[f'SFP_A_FA_E_{trxn_curr}_CUM_UGLΔFV_{sec_code}', (trxn_quan / unitsheld_t0) * SFP_A_FA_E_curr_CUM_UGLΔFV_t0,
                                                f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', (trxn_quan / unitsheld_t0) * SFP_A_FA_E_curr_CUM_UGLΔFV_t0]]
                                      )        
        ################
        ################
        if rgl_t1 == 1: ## realized gain, so we credit the realized gain
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 
                                             'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                            self.fillempty, self.fillempty, 
                                           f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0))]]
                                    )
        elif rgl_t1 == -1: ## realized loss, so we debit the realized loss
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 
                                             'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                            f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0)), 
                                           self.fillempty, self.fillempty]]
                                    )
        else: ## rgl_t1 == 0; ## breakeven, so we do not need to record a realized gain/loss
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1'],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0)]]
                                    )

        merged_je_rows = pd.concat([je_dfrow_0,je_dfrow_1],axis=1)
        return merged_je_rows
    
    def func_FAOL_open(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        trxn_quan = transaction['Trxn_quantity']
        
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SFP_A_FA_D_{transcurr}_BV_{sec_code}', transval, 
                                       f'SCF_OA_PPI_{transcurr}_{sec_code}', transval]]
                                )
        return je_dfrow    
        
def func_FAOL_close(self, idx, exp, ae, exe, cs, cp, 
                    avgbp_t0, unitsheld_t0, SFP_A_FA_O_curr_CUM_UGLΔFV_t0, 
                    underlying_sec_code, underlying_Price, underlying_K, option_multiplier):
    '''
    avgbp_t0: average book price for ONE CONTRACT (NOT SAME AS CONTRACT PRICE, because contract price does not include fees
    and only corresponds to the price of one underlying share, whereas the BOOK PRICE of ONE CONTRACT includes fees and corresponds
    to the price of 100 (option_multiplier) underlying shares, which is the contract size for most options)
    '''
    if not isinstance(cp, str):
        raise TypeError(f"'cp' must be a string, got {type(cp).__name__}")
    cp = cp.lower()  # Normalize
    if cp in ['c', 'call','认购','购']:
        cp = 'call'
    elif cp in ['p', 'put','认沽','沽']:
        cp = 'put'
    else:
        raise ValueError(f"Invalid cp value: {cp}")   
    ##################################################``
    if not isinstance(ae, str):
        raise TypeError(f"'ae' must be a string, got {type(ae).__name__}")
    ae = ae.lower() ## https://www.schwab.com/learn/story/options-expiration-definitions-checklist-more ## https://licai.cofool.com/ask/qa_1414653.html
    if ae in ['a', 'american','美式','美']: ## Standard U.S. equity options (options on single-name stocks) are American-style. 
        ae = 'american' ## 属于美式期权的品种有橡胶期权、铝期权、锌期权、豆粕期权、玉米期权、铁矿石期权、石油气期权、聚丙烯期权、聚氯乙烯期权、聚乙烯期权、白糖期权、棉花期权、PTA期权、甲醇期权、菜籽粕期权和动力煤期权。
    elif ae in ['e', 'european','euro','欧式','欧']: ## Most options on stock indexes, such as the Nasdaq-100® (NDX), S&P 500® (SPX), and Russell 2000® (RUT), are European-style.
        ae = 'european' ## 欧式期权中包括的就是中金所股指期货期权为欧式，50ETF期权、沪市300ETF期权、深市300ETF期权、沪深300股指期权、黄金期权、铜期权
    else:
        raise ValueError(f"Invalid ae value: {ae}")    
    ##################################################
    if not isinstance(cs, bool): ## cash settlement; standard equity options are not cash-settled——actual shares are transferred in an exercise/assignment. 
        ## Options on broad-based indexes, however, are cash-settled in an amount equal to the difference between the settlement price of the index and the strike price of the option times the contract multiplier.
        raise TypeError(f"'exp' must be a boolean, got {type(cs).__name__}")
    ##################################################
    if not isinstance(exp, bool):
        raise TypeError(f"'exp' must be a boolean, got {type(exp).__name__}")
    ##################################################
    if not isinstance(exe, bool):
        raise TypeError(f"'exp' must be a boolean, got {type(exe).__name__}")
    ##################################################
    ##################################################
    transaction = self.df.iloc[idx]
    trxn_val = transaction['Trxn_value']
    trxn_curr = transaction['Trxn_value_curr']
    sec_code = transaction['Security_code']
    trxn_quan = transaction['Trxn_quantity']

    ugl_t0 = 0 ## unrealized g/l for period t0 (last period); 1 for gain DR, -1 for loss CR, 0 for breakeven
    if SFP_A_FA_O_curr_CUM_UGLΔFV_t0 > 0:
        ugl_t0 = 1 
    elif SFP_A_FA_O_curr_CUM_UGLΔFV_t0 < 0:
        ugl_t0 = -1

    if not exp:
        if ae == 'american':
            if exe:
                if cs: ## cash settlement; similar to func_close_FAE() but without the need for a new long equity position
                    pass
                else: ## cs == 0; equity settlement; we actually get stock 
                    pass
            else: ## exe == 0; long option position closed but due to neither expiration nor execution; similar to closing of a long equity position
                rgl_t1 = 0 ## realized g/l for period t1 (current period); 1 for gain, -1 for loss, 0 for breakeven
                if trxn_val > (trxn_quan * avgbp_t0):
                    rgl_t1 = 1 ## realized a gain upon closing this position
                elif trxn_val < (trxn_quan * avgbp_t0):
                    rgl_t1 = -1 ## realized a loss upon closing this position
                if ugl_t0 == 0: ## close out unrealized gain
                    je_dfrow_0 = pd.DataFrame(  index=[idx],
                                                columns=[   'DR_account_0', 'DR_value_0', 
                                                            'CR_account_0', 'CR_value_0',],
                                                data=[[ f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                        f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0]]
                                          )
                elif ugl_t0 == -1: ## close out unrealized loss
                    je_dfrow_0 = pd.DataFrame(  index=[idx],
                                                columns=[   'DR_account_0', 'DR_value_0', 
                                                            'CR_account_0', 'CR_value_0',],
                                                data=[[ f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                        f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,]]
                                          )
                if rgl_t1 == 1: ## realized gain, so we credit the realized gain
                    je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 
                                             'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                            self.fillempty, self.fillempty, 
                                           f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0))]]
                                    )
                elif rgl_t1 == -1: ## realized loss, so we debit the realized loss
                    je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1', 
                                             'DR_account_2', 'DR_value_2', 
                                             'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                            f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0)), 
                                           self.fillempty, self.fillempty]]
                                    )
                else: ## rgl_t1 == 0; ## breakeven, so we do not need to record a realized gain/loss
                    je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 
                                             'CR_account_1', 'CR_value_1'],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                           f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0)]]
                                    )
                je_dfrow = pd.concat([je_dfrow_0, je_dfrow_1], axis=1) ## combine the two JE rows into one DataFrame
                return je_dfrow
        else: ## ae == 'european'; if long option position closed but due to neither expiration nor execution;
            ## then we must've sold it; similar to closing of a long equity position
            rgl_t1 = 0 ## realized g/l for period t1 (current period); 1 for gain, -1 for loss, 0 for breakeven
            if trxn_val > (trxn_quan * avgbp_t0):
                rgl_t1 = 1 ## realized a gain upon closing this position
            elif trxn_val < (trxn_quan * avgbp_t0):
                rgl_t1 = -1 ## realized a loss upon closing this position
            if ugl_t0 == 0: ## close out unrealized gain
                je_dfrow_0 = pd.DataFrame(  index=[idx],
                                            columns=[   'DR_account_0', 'DR_value_0', 
                                                        'CR_account_0', 'CR_value_0',],
                                            data=[[ f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0]]
                                        )
            elif ugl_t0 == -1: ## close out unrealized loss
                je_dfrow_0 = pd.DataFrame(  index=[idx],
                                            columns=[   'DR_account_0', 'DR_value_0', 
                                                        'CR_account_0', 'CR_value_0',],
                                            data=[[ f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,]]
                                        )
            if rgl_t1 == 1: ## realized gain, so we credit the realized gain
                je_dfrow_1 = pd.DataFrame(index=[idx],
                                columns=['DR_account_1', 'DR_value_1', 
                                            'CR_account_1', 'CR_value_1', 
                                        'DR_account_2', 'DR_value_2', 
                                            'CR_account_2', 'CR_value_2',],
                                data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                        f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                        self.fillempty, self.fillempty, 
                                        f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0))]]
                                )
            elif rgl_t1 == -1: ## realized loss, so we debit the realized loss
                je_dfrow_1 = pd.DataFrame(index=[idx],
                                columns=['DR_account_1', 'DR_value_1', 
                                            'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 
                                            'CR_account_2', 'CR_value_2',],
                                data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                        f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0),
                                        f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (trxn_quan * avgbp_t0)), 
                                        self.fillempty, self.fillempty]]
                                )
            else: ## rgl_t1 == 0; ## breakeven, so we do not need to record a realized gain/loss
                je_dfrow_1 = pd.DataFrame(index=[idx],
                                columns=['DR_account_1', 'DR_value_1', 
                                            'CR_account_1', 'CR_value_1'],
                                data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, 
                                        f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', (trxn_quan * avgbp_t0)]]
                                )
            je_dfrow = pd.concat([je_dfrow_0, je_dfrow_1], axis=1) ## combine the two JE rows into one DataFrame
            return je_dfrow 
            
    if exp:
        if exe: 
            if cs: ## cash settlement;
                if ugl_t0 == 1: ## close out unrealized gain
                    pass
                elif ugl_t0 == -1: ## close out unrealized loss
                    pass
                if cp == 'call':
                    if underlying_Price > (underlying_K + avgbp_t0/option_multiplier): ## condition for a realized gain on an ITM call option
                        rgl_t1_val = (underlying_Price - (underlying_K + avgbp_t0/option_multiplier)) * option_multiplier * trxn_quan
                        rgl_t1_val = np.abs(rgl_t1_val)
                        pass
                    else: ## underlying price > underlying K but the difference < avgbp_t0/option_multiplier ## condition for a realized loss on an ITM call option
                        rgl_t1_val = (underlying_Price - (underlying_K + avgbp_t0/option_multiplier)) * option_multiplier * trxn_quan
                        rgl_t1_val = np.abs(rgl_t1_val)
                        pass
                else: ## cp == 'put'
                    if underlying_Price < (underlying_K - avgbp_t0/option_multiplier): ## condition for a realized gain on an ITM put option
                        rgl_t1_val = (underlying_K - (underlying_Price + avgbp_t0/option_multiplier)) * option_multiplier * trxn_quan
                        rgl_t1_val = np.abs(rgl_t1_val)
                        pass
                    else: ## underlying price < underlying K but the difference < avgbp_t0/option_multiplier ## condition for a realized loss on an ITM put option
                        rgl_t1_val = (underlying_K - (underlying_Price + avgbp_t0/option_multiplier)) * option_multiplier * trxn_quan
                        rgl_t1_val = np.abs(rgl_t1_val)
                        pass

            else: ## cs == 0; equity settlement; we actually get stock
                if ugl_t0 == 1: ## close out unrealized gain
                    pass
                elif ugl_t0 == -1: ## close out unrealized loss
                    pass
                if cp == 'call':
                    pass
                else: ## cp == 'put'
                    pass
        else: ## exe == 0; long option position closed because of expiration; OTM; no exercise, option expires worthless
            if SFP_A_FA_O_curr_CUM_UGLΔFV_t0 > 0: ## close out unrealized gain
                je_dfrow = pd.DataFrame(  index=[idx],
                                            columns=[   'DR_account_0', 'DR_value_0', 
                                                        'CR_account_0', 'CR_value_0',
                                                        'DR_account_1', 'DR_value_1',
                                                        'CR_account_1', 'CR_value_1'],
                                            data=[[ f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SCI_I_RGLFA_{trxn_curr}', avgbp_t0 * trxn_quan,
                                                    f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', avgbp_t0 * trxn_quan]]
                                      )
            elif SFP_A_FA_O_curr_CUM_UGLΔFV_t0 < 0: ## close out unrealized loss
                je_dfrow = pd.DataFrame(  index=[idx],
                                            columns=[   'DR_account_0', 'DR_value_0', 
                                                        'CR_account_0', 'CR_value_0',
                                                        'DR_account_1', 'DR_value_1',
                                                        'CR_account_1', 'CR_value_1'],
                                            data=[[ f'SFP_A_FA_O_{trxn_curr}_CUM_UGLΔFV_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}', SFP_A_FA_O_curr_CUM_UGLΔFV_t0,
                                                    f'SCI_I_RGLFA_{trxn_curr}', avgbp_t0 * trxn_quan,
                                                    f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', avgbp_t0 * trxn_quan]]
                                      )
            else: ## SFP_A_FA_O_curr_CUM_UGLΔFV_t0 == 0; we do not need to close out any unrealized gain/loss
                je_dfrow = pd.DataFrame(  index=[idx],
                                            columns=[   'DR_account_0', 'DR_value_0', 
                                                        'CR_account_0', 'CR_value_0'],
                                            data=[[ f'SCI_I_RGLFA_{trxn_curr}', avgbp_t0 * trxn_quan,
                                                    f'SFP_A_FA_O_{trxn_curr}_BV_{sec_code}', avgbp_t0 * trxn_quan]]
                                      )
            return je_dfrow

        


    
    
    def func_FAOS_open(self, idx, cp):
        ## prepaid cash, future liability 

    def func_misc_fee(self, idx): ## miscellaneous fees ## 杂费 ## bank fee, ADR fee, transfer fee, custodian fee
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        description = transaction['Description']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0'],
                                data=[[f'SCI_E_OF_{trxn_curr}', 
                                       trxn_val, 
                                       f'SCF_OA_OEP_{trxn_curr}', 
                                       trxn_val]],
                                )
        return je_dfrow, description
        
    def func_curr_tf(self, idx, presentation_curr):
        transaction = self.df.iloc[idx]
        quote_val = transaction['Trxn_value'] ## quote (end-result) currency value
        quote_curr = transaction['Trxn_value_curr'] ## quote (end-result) currency
        base_val = transaction['Trxn_quantity'] ## base (original) currency value
        base_curr = transaction['Trxn_quantity_unit'] ## base (original) currency
        xrate = transaction['Trxn_price'] ## exchange rate 
        xrate_curr = transaction['Trxn_price_curr'] ## exchange rate currency codes, QUOTE/BASE
        xr_lastmonth = self.XR0_df.loc[quote_curr, base_curr]
        
        if xrate > xr_lastmonth: ## condition for gain in currency translation
            gain_in_Qcurr = (xrate - xr_lastmonth) * base_val ## gain amount stated in the Quote currency
            gain_in_Bcurr = gain_in_Qcurr / xr_lastmonth ## gain amount stated in the Base currency
            if quote_curr == presentation_curr:
                gain_recorded = gain_in_Qcurr
            elif base_curr == presentation_curr:
                gain_recorded = gain_in_Bcurr
            else: ## neither QUOTE nor BASE is in the presentation currency (HKD), eg. CNY/USD pair
                gain_recorded = gain_in_Qcurr * self.XR0_df.loc[presentation_curr, quote_curr]
            je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0', 
                                         'CR_account_1', 'CR_value_1'],
                                data=[[f'SFP_A_CCE_{quote_curr}', quote_val,
                                       f'SFP_A_CCE_{base_curr}', base_val,
                                       f'SCI_XRPLFXC_{presentation_curr}',gain_recorded]]
                                )
        if xrate < xr_lastmonth: ## condition for loss in currency translation    
            loss_in_Qcurr = (xrate - xr_lastmonth) * base_val ## loss amount stated in the Quote currency
            loss_in_Bcurr = loss_in_Qcurr / xr_lastmonth ## loss amount stated in the Base currency
            if quote_curr == presentation_curr:
                loss_recorded = loss_in_Qcurr
            elif base_curr == presentation_curr:
                loss_recorded = loss_in_Bcurr
            else: ## neither QUOTE nor BASE is in the presentation currency (HKD), eg. CNY/USD pair
                loss_recorded = loss_in_Qcurr * self.XR0_df.loc[presentation_curr, quote_curr]
            je_dfrow = pd.DataFrame(index=[idx],
                                    columns=['DR_account_0', 'DR_value_0', 
                                             'CR_account_0', 'CR_value_0', 
                                             'DR_account_1', 'DR_value_1'],
                                    data=[[f'SFP_A_CCE_{quote_curr}', quote_val,
                                           f'SFP_A_CCE_{base_curr}', base_val,
                                           f'SCI_XRPLFXC_{presentation_curr}',loss_recorded]]
                                    )
        if xrate == xr_lastmonth:
            je_dfrow = pd.DataFrame(index=[idx],
                        columns=['DR_account_0', 'DR_value_0', 
                                 'CR_account_0', 'CR_value_0'],
                        data=[[f'SFP_A_CCE_{quote_curr}', quote_val,
                               f'SFP_A_CCE_{base_curr}', base_val]]
                        )
            
        return je_dfrow      
        
    def func_accn_tf(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCI_E_TF_{trxn_curr}', trxn_val, 
                                       f'SCF_OA_OEP_{trxn_curr}', trxn_val]]
                                )
        return je_dfrow      

    def func_sub(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCF_FA_SR_{trxn_curr}', trxn_val, 
                                       f'SCNAV_SUB_{trxn_curr}', trxn_val]]
                                )
        return je_dfrow     

    def func_red(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCNAV_RED_{trxn_curr}', trxn_val, 
                                       f'SCF_FA_RP_{trxn_curr}', trxn_val]]
                                )
        return je_dfrow  

    def func_bank_fee(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCI_E_AF_{trxn_curr}', trxn_val, 
                                       f'SCF_OA_OEP_{trxn_curr}', trxn_val]]
                                )
        return je_dfrow  

    def func_bank_rebate(self, idx):
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCF_OA_OEP_{trxn_curr}', trxn_val, 
                                       f'SCI_E_AF_{trxn_curr}', trxn_val]]
                                )
        return je_dfrow  

    def func_ADR_fee(self, idx): ## ADR 管理费
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 
                                         'CR_account_0', 'CR_value_0'],
                                data=[[f'SCI_E_OF_{trxn_curr}', trxn_val, 
                                       f'SCF_OA_OEP_{trxn_curr}', trxn_val]]
                                )

    
    

