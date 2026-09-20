#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codigo para saber la calidad de los datos de ghana
@author: vrobledodelgado
"""


#Libraries
import numpy as np
import pandas as pd
from datetime import timedelta
import glob
import time
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, AutoDateLocator

def read_process_data(file):
    try:
        data = pd.read_csv(file, delimiter=';') 
    except:
        print('Can not open: '+file[len(prefix):])
        pass
    
    if file.startswith("./GaugeStations/gauges/15"):
        data['date'] = pd.to_datetime(data['date'], format='%Y-%m-%d')
        #data['date'] = data['date'].dt.strftime('%Y-%m-%d')
    else:
        data['date'] = pd.to_datetime(data['date'], format='%d-%b-%y')
        data['date'] = data['date'].dt.strftime('%Y-%m-%d')
        data['date'] = pd.to_datetime(data['date'], format='%Y-%m-%d')
    data.set_index('date', inplace=True)
    data.sort_index(inplace=True)
    
    # Reemplaza los valores vacíos con NaN
    data['discharge'] = pd.to_numeric(data['discharge'], errors='coerce')
    data['discharge'] = data['discharge'].replace(-999.000, np.NaN)
    data.to_csv(mydir+"fixeddata/"+file[len(prefix):])
    return data

def figure(file,data,init,end,nanpercentage):
    fig = plt.subplots(figsize=(16, 5))
    plt.plot(data.index, data['discharge'], label=file[len(prefix):])
    plt.xlabel('Date', fontsize=15)
    plt.ylabel('Discharge (m^3/s)',fontsize=15)
    plt.xticks(rotation=30, fontsize=15)
    plt.xlim(init, end)
    plt.title(file[len(prefix):])
   # plt.text(0.5, 0.9, f"Start Date: {init}\nEnd Date: {end}\nNaN percentage: {nanpercentage}", 
    #         fontsize=10, bbox=dict(facecolor='white', alpha=0.5))
    plt.text(0.05, 0.95, f"Start Date: {init}\nEnd Date: {end}\nNaN percentage: {nanpercentage}", 
         fontsize=10, bbox=dict(facecolor='white', alpha=0.5), transform=plt.gca().transAxes,
         verticalalignment='top')
    ax = plt.gca()
    ax.xaxis.set_major_locator(AutoDateLocator(minticks=10, maxticks=20))
    ax.xaxis.set_major_formatter(DateFormatter('%Y-%m'))
    plt.savefig(mydir+"plots/"+file[len(prefix):]+'.png',bbox_inches='tight')
    plt.show()

#read all the files
mydir = "./GaugeStations/gauges/"
file_list = glob.glob(mydir + "*.txt")
print((file_list))
prefix = './GaugeStations/gauges/'
    
for file in file_list:
    print('Opening: ' + file[len(prefix):])
    data = read_process_data(file)
    #count nan values
    nan_count = data['discharge'].isnull().sum()
    #calculando porcentaje de faltantes
    nonulldata = data['discharge'].notnull().sum()
    totaldata = len(data)
    nanpercentage = (nan_count*100)/totaldata
    print('nan percentage: ',nanpercentage)
    init = data.index[0]
    end = data.index[-1]
    print("init: ",init ,' ends: ',end)
    figure(file,data,init,end,nanpercentage)
