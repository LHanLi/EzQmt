# 自动启动国金qmt客户端
import os
import time
import win32gui, win32api, win32con

# 适用于国金qmt，登录需要时间，如自动运行多个qmt请间隔足够长时间

user='   '                                                             # 填入您的qmt用户名
password='   '                                                         # 填入您的qmt密码
cmdstr="start D:\\国金证券QMT交易端111\\bin.x64\\XtItClient.exe "       # 填入您的qmt路径


def input_content(hwd, content):
  mylist=[int(ord(item)) for item in str(content)]
  for item in mylist:
      click_keys(hwd,item)
  time.sleep(0.1)

def get_my_child_window(parent):
    hwndChildList = []
    win32gui.EnumChildWindows(
        parent, lambda hwnd, param: param.append((hwnd,win32gui.GetWindowText(hwnd),win32gui.GetClassName(hwnd),win32gui.GetWindowRect(hwnd))),  hwndChildList)
    for i in range(len(hwndChildList)):
        item=hwndChildList[i]
        #print item[0],item[1],item[2],i
    return hwndChildList
  
def find_child_window(parent_handle,winstr,classname=""):
    result=[]                
    handlelist=get_my_child_window(parent_handle)
    for item in handlelist:
        if item[1].strip().startswith(winstr):
            if classname=="":
                result.append(item[0])
            else:
                if str(item[2])==classname:
                    result.append(item[0])
    return result

def click_keys(hwd, mykey):
  win32api.SendMessage(hwd, win32con.WM_KEYDOWN, mykey, 0)
  win32api.SendMessage(hwd, win32con.WM_KEYUP, mykey, 0)

# 进入qmt文件夹
os.system(cmdstr)
# 获取qmt句柄
qmt_handle=find_child_window(0,u"国金证券QMT交易端","Qt5QWindowIcon")[0]
time.sleep(2)
# 后台输入账号
input_content(qmt_handle,str(user))
time.sleep(2)
click_keys(qmt_handle,win32con.VK_RETURN)
time.sleep(2)
# 后台输入密码
input_content(qmt_handle,str(password))
time.sleep(2)
click_keys(qmt_handle,win32con.VK_RETURN)
