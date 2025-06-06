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
    def __init__(self, df, fillempty=''):
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

    def concat_je_rows(*dfs): ## variable-length arguments, *args 
        """
        Use as: 
            df_combined = concat_je_rows(df1, df2, df3, df4, ...)
                or
            df_list = [df1, df2, df3]
            df_combined = concat_je_rows(*df_list)
        """
        merged_df = pd.concat(dfs, axis=1, sort=False)
        value_cols = [col for col in merged_df.columns if 'value' in col]
        merged_df[value_cols] = merged_df[value_cols].applymap(
            lambda x: float(f"{x:.2f}") if isinstance(x, (int, float)) else x
        )
        merged_df = merged_df.fillna(self.fillempty)
        return merged_df
    
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

    def func_open_FAE(self, idx): ## open financial asset equity ## 建仓金融资产权益
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0'],
                                data=[[f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', trxn_val, f'SCF_OA_PPI_{trxn_curr}_{sec_code}',trxn_val]]
                                )
        return je_dfrow      

    def func_close_FAE(self, idx, avgbp_t0, unitsheld_t0, SFP_A_FA_E_USD_CUM_UGLΔFV_t0): ## close financial asset equity ## 平仓金融资产权益
        ## avgbp_t0 = average book price (per share) from last period
        ## unitsheld_t0 = number of units of security (shares) held on the books in the last period
        ## SFP_A_FA_E_USD_CUM_UGLΔFV_t0 = cumulative unrealized gain or loss at fair value from last period (this is an adjunct asset account); 
        ### we need to close this account out by the pro rata portion; positive value implies a DR balance and negative value implies a CR balance
        ## the 3 inputs avgbp_t0, unitsheld_t0, SFP_A_FA_E_USD_CUM_UGLΔFV_t0 must be sourced from the previous period's Investment Schedule

        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        transquan = transaction['Trxn_quantity']
        
        ugl_t0 = 0 ## unrealized g/l for period t0 (last period); 1 for gain DR, -1 for loss CR, 0 for breakeven
        if SFP_A_FA_E_USD_CUM_UGLΔFV_t0 > 0:
            ugl_t0 = 1 
        elif SFP_A_FA_E_USD_CUM_UGLΔFV_t0 < 0:
            ugl_t0 = -1

        rgl_t1 = 0 ## realized g/l for period t1 (current period); 1 for gain, -1 for loss, 0 for breakeven
        if trxn_val > (transquan * avgbp_t0):
            rgl_t1 = 1 ## realized a gain upon closing this position
        elif trxn_val < (transquan * avgbp_t0):
            rgl_t1 = -1 ## realized a loss upon closing this position
        ################
        ################
        ## first we need to close out the unrealized gain/loss account; this is a pro rata portion of the cumulative unrealized gain/loss account
        if ugl_t0 == 1: ## implies a DR balance, so we must have SFP_A_FA_E_curr_CUM_UGLΔFV on CR to close out the DR balance
            je_dfrow_0 = pd.DataFrame(  index=[idx],
                                        columns=['DR_account_0', 
                                                'DR_value_0', 
                                                'CR_account_0', 
                                                'CR_value_0'],
                                        data=[[f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}',
                                            (transquan / unitsheld_t0) * SFP_A_FA_E_USD_CUM_UGLΔFV_t0,
                                            f'SFP_A_FA_E_{trxn_curr}_CUM_UGLΔFV_{sec_code}',
                                            (transquan / unitsheld_t0) * SFP_A_FA_E_USD_CUM_UGLΔFV_t0]]
                                      )

        elif ugl_t0 == -1: ## implies a CR balance, so we must have SFP_A_FA_E_curr_CUM_UGLΔFV on DR to close out the CR balance
            je_dfrow_0 = pd.DataFrame(  index=[idx],
                                        columns=['DR_account_0', 
                                                'DR_value_0', 
                                                'CR_account_0', 
                                                'CR_value_0'],
                                        data=[[f'SFP_A_FA_E_{trxn_curr}_CUM_UGLΔFV_{sec_code}',
                                                (transquan / unitsheld_t0) * SFP_A_FA_E_USD_CUM_UGLΔFV_t0,
                                                f'SCI_OCI_UGLFA_ΔFV_{trxn_curr}_{sec_code}',
                                                (transquan / unitsheld_t0) * SFP_A_FA_E_USD_CUM_UGLΔFV_t0]]
                                      )        
        ################
        ################
        if rgl_t1 == 1: ## realized gain, so we credit the realized gain
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (transquan * avgbp_t0),
                                            self.fillempty, self.fillempty, f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (transquan * avgbp_t0))]]
                                    )
        elif rgl_t1 == -1: ## realized loss, so we debit the realized loss
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 'CR_account_1', 'CR_value_1', 
                                            'DR_account_2', 'DR_value_2', 'CR_account_2', 'CR_value_2',],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (transquan * avgbp_t0),
                                            f'SCI_I_RGLFA_{trxn_curr}', (trxn_val - (transquan * avgbp_t0)), self.fillempty, self.fillempty]]
                                    )
        else: ## rgl_t1 == 0; ## breakeven, so we do not need to record a realized gain/loss
            je_dfrow_1 = pd.DataFrame(index=[idx],
                                    columns=['DR_account_1', 'DR_value_1', 'CR_account_1', 'CR_value_1'],
                                    data=[[f'SCF_OA_PSI_{trxn_curr}_{sec_code}', trxn_val, f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', (transquan * avgbp_t0)]]
                                    )

        merged_je_rows = self.concat_je_rows(je_dfrow_0,je_dfrow_1)
        return merged_je_rows
    
    # def func_open_FAOL(self, idx):
    #     transaction = self.df.iloc[idx]
    #     transval = transaction['Transaction_value']
    #     transcurr = transaction['Trans_value_curr']
    #     sec_code = transaction['Security_code']
        
    #     je_dfrow = pd.DataFrame(index=[idx],
    #                             columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0'],
    #                             data=[[f'SFP_A_FA_D_{transcurr}_BV_{sec_code}', transval, f'SCF_OA_PPI_{transcurr}_{sec_code}',transval]]
    #                             )
    #     return je_dfrow      

    # def func_close_FAOL(self, idx, cp, ae, cs, exp, exe):
    #     if not isinstance(cp, str):
    #         raise TypeError(f"'cp' must be a string, got {type(cp).__name__}")
        
    #     if not isinstance(cs, bool): ## cash settlement; standard equity options are not cash-settled—actual shares are transferred in an exercise/assignment. 
    #         ## Options on broad-based indexes, however, are cash-settled in an amount equal to the difference between the settlement price of the index and the strike price of the option times the contract multiplier.
    #         raise TypeError(f"'exp' must be a boolean, got {type(cs).__name__}")

    #     if not isinstance(exp, bool):
    #         raise TypeError(f"'exp' must be a boolean, got {type(exp).__name__}")
       
    #     if not isinstance(exe, bool):
    #         raise TypeError(f"'exp' must be a boolean, got {type(exe).__name__}")
        
    #     cp = cp.lower()  # Normalize
    #     if cp in ['c', 'call','认购','购']:
    #         cp = 'call'
    #     elif cp in ['p', 'put','认沽','沽']:
    #         cp = 'put'
    #     else:
    #         raise ValueError(f"Invalid cp value: {cp}")       
        
    #     ae = ae.lower() ## https://www.schwab.com/learn/story/options-expiration-definitions-checklist-more ## https://licai.cofool.com/ask/qa_1414653.html
    #     if ae in ['a', 'american','美式','美']: ## Standard U.S. equity options (options on single-name stocks) are American-style. 
    #         ae = 'american' ## 属于美式期权的品种有橡胶期权、铝期权、锌期权、豆粕期权、玉米期权、铁矿石期权、石油气期权、聚丙烯期权、聚氯乙烯期权、聚乙烯期权、白糖期权、棉花期权、PTA期权、甲醇期权、菜籽粕期权和动力煤期权。
    #     elif ae in ['e', 'european','euro','欧式','欧']: ## Most options on stock indexes, such as the Nasdaq-100® (NDX), S&P 500® (SPX), and Russell 2000® (RUT), are European-style.
    #         ae = 'european' ## 欧式期权中包括的就是中金所股指期货期权为欧式，50ETF期权、沪市300ETF期权、深市300ETF期权、沪深300股指期权、黄金期权、铜期权
    #     else:
    #         raise ValueError(f"Invalid cp value: {cp}")      
    #     ####################
    #     transaction = self.df.iloc[idx]
    #     transval = transaction['Transaction_value']
    #     transcurr = transaction['Trans_value_curr']
    #     sec_code = transaction['Security_code']
    #     if exp and exe: ## long option position exercised at expiration; ITM
    #         if cs:
            
    #         if not cs:


    #     elif exp and not exe: ## long option position closed because of expiration; OTM
        
    #     elif not exp and exe and ae == 'american': ## long option position closed because of exercise before expiration

    #     else: ## closed out neither from expiration nor exercise; sold option contract itself; similar to func_close_FAE()    

    def func_close_FAOL(self, idx, cp, exp):
        if not isinstance(cp, str):
            raise TypeError(f"'cp' must be a string, got {type(cp).__name__}")
        cp = cp.lower()  # Normalize
        if cp in ['c', 'call','认购','购']:
            return 'call'
        elif cp in ['p', 'put','认沽','沽']:
            return 'put'
        else:
            raise ValueError(f"Invalid cp value: {cp}")
        if not isinstance(exp, bool):
            raise TypeError(f"'exp' must be a boolean, got {type(exp).__name__}")
        ####################
        transaction = self.df.iloc[idx]
        trxn_val = transaction['Trxn_value']
        trxn_curr = transaction['Trxn_value_curr']
        sec_code = transaction['Security_code']
        


    
    
    def func_open_FAOS(self, idx, cp):
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
        
    def func_curr_tf(self, idx, xr_lastmonth):
        transaction = self.df.iloc[idx]
        quote_val = transaction['Trxn_value'] ## quote (end-result) currency value
        quote_curr = transaction['Trxn_value_curr'] ## quote (end-result) currency
        base_val = transaction['Trxn_quantity'] ## base (original) currency value
        base_curr = transaction['Trxn_quantity_unit'] ## base (original) currency
        xrate = transaction['Trxn_price'] ## exchange rate 
        xrate_curr = transaction['Trxn_price_curr'] ## exchange rate currency codes, QUOTE/BASE
        xr_lastmonth = re.search(r'[\d.]+', xr_lastmonth)
        xr_lastmonth = xr_lastmonth.group() if xr_lastmonth else None
        
        if xrate > xr_lastmonth: ## condition for gain in currency translation
                je_dfrow = pd.DataFrame(index=[idx],
                                columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0', 'CR_account_1', 'CR_value_1'],
                                data=[[f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', trxn_val, f'SCF_OA_PPI_{trxn_curr}_{sec_code}',trxn_val]]
                                )
        if xrate < xr_lastmonth: ## condition for loss in currency translation    
            je_dfrow = pd.DataFrame(index=[idx],
                                    columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0', 'DR_account_1', 'DR_value_1'],
                                    data=[[f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', trxn_val, f'SCF_OA_PPI_{trxn_curr}_{sec_code}',trxn_val]]
                                    )
        if xrate == xr_lastmonth:
            je_dfrow = pd.DataFrame(index=[idx],
                        columns=['DR_account_0', 'DR_value_0', 'CR_account_0', 'CR_value_0', 'DR_account_1', 'DR_value_1'],
                        data=[[f'SFP_A_FA_E_{trxn_curr}_BV_{sec_code}', trxn_val, f'SCF_OA_PPI_{trxn_curr}_{sec_code}',trxn_val]]
                        )
            
        return je_dfrow      
        
        
        
    def func_FAE_mtmadj(self, df):  ## month-to-month adjustments ## 月末调整
        ## this does not require iterating through the df
        ## considering writing this function under another class called 'IS monthly/periodic adjustments' or something
    
    def tabulate_ledgers(self):
