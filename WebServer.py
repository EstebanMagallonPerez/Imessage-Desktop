import logging
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import threading
import keyboard
import asyncio
import sys
from tornado.options import define, options
from PIL import Image, ImageDraw
from pystray import Icon as icon, Menu as menu, MenuItem as item
import requests
import paramiko
import time
from win10toast import ToastNotifier
toaster = ToastNotifier()

phoneIP = "10.0.0.227"
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(phoneIP, username="root", password="alpine")
command = 'clsms "Test" 5105662843' 
currentThreadID = -1


define("port", default=1111, help="run on the given port", type=int)

closeThreads =  False
def start():
	def getSideFromPhone():
		global ssh
		data = ""
		error = None
		#print("getting side")
		ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("sqlite3 -header ../mobile/Library/SMS/sms.db <<EOF\n"+
					".mode insert\n"+
					"Select display_name, message.ROWID, message.handle_id, chat_identifier,text from message, chat, chat_handle_join, chat_message_join where chat.ROWID = chat_handle_join.chat_id AND chat_handle_join.handle_id = message.handle_id AND chat.ROWID = chat_message_join.chat_id AND message_id = message.ROWID GROUP BY chat_identifier ORDER BY date DESC;\n"+
					"EOF\n")

		output = ""
		for line in ssh_stdout:
		# Process each line in the remote output
			output+=line
			#print(line)
		#print(output)
		return output


	def getMessagesFromPhone(chat_identifier):
		global ssh
		data = ""
		error = None
		#print("getting content")
		ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("sqlite3 -header ../mobile/Library/SMS/sms.db <<EOF\n"+
					".mode insert\n"+
					"Select is_from_me,service,text from message, chat, chat_handle_join, chat_message_join where chat.ROWID = chat_handle_join.chat_id AND chat_handle_join.handle_id = message.handle_id AND chat.ROWID = chat_message_join.chat_id AND message_id = message.ROWID AND chat_identifier = '"+chat_identifier+"' ORDER BY date DESC LIMIT 50;\n"+
					"EOF\n")

		output = ""
		for line in ssh_stdout:
		# Process each line in the remote output
			output+=line
		#print("messages are: ",output)
		return output

	def updateSide():
		output = []
		data = getSideFromPhone()
		#print(data)
		data = data.split("INSERT INTO \"table\"(display_name,ROWID,handle_id,chat_identifier,text) VALUES(")
		for elem in data:
			if elem == "":
				continue
			currentIndex = 0
			#print("elem:",elem)
			tempVal = elem.replace("INSERT INTO \"table\"(display_name,ROWID,handle_id,chat_identifier,text) VALUES(","").replace(");","")
			#print("tempVal:",tempVal)
			#get displayName
			endIndex = tempVal.index(",")
			display_name = tempVal[currentIndex:endIndex]
			display_name = display_name[1:-1]
			currentIndex = endIndex+1
			#print("displayName is: ",display_name)
			#get row id
			endIndex = tempVal.index(",",currentIndex)
			rowID = tempVal[currentIndex:endIndex]
			#print("rowID",rowID)
			currentIndex = endIndex+1
			#get handle id
			endIndex = tempVal.index(",",currentIndex)
			handle_id = tempVal[currentIndex:endIndex]
			currentIndex = endIndex+1
			#print("handle_id",handle_id)
			#get chat idenentifier
			endIndex = tempVal.index(",",currentIndex)
			chat_identifier = tempVal[currentIndex:endIndex]
			chat_identifier = chat_identifier.replace("'","")
			currentIndex = endIndex+1
			#print("chat_identifier",chat_identifier)
			#get message text
			text = tempVal[currentIndex:]
			text = text[1:-2]
			#print(tempVal)
			#print(rowID,handle_id,chat_identifier,text)
			output.append({"display_name":display_name,"rowID":rowID, "handle_id":handle_id, "chat_identifier":chat_identifier,"text":text})
		KeyboardSocketHandler.send_updates({"type":"side","data":output})

	def updateMessageThread(message_id):
		global currentThreadID
		currentThreadID = message_id
		output = []
		data = getMessagesFromPhone(message_id)
		data = data.split("INSERT INTO \"table\"(is_from_me,service,text) VALUES(")
		for elem in data:
			if elem == "":
				continue
			currentIndex = 0
			#print("elem:",elem)
			tempVal = elem.replace("INSERT INTO \"table\"(is_from_me,service,text) VALUES(","").replace(");","")
			#print("tempVal:",tempVal)
			#get is from Me
			endIndex = tempVal.index(",")
			is_from_me = tempVal[currentIndex:endIndex]
			currentIndex = endIndex+1
			#get service
			endIndex = tempVal.index(",",currentIndex)
			service = tempVal[currentIndex:endIndex]
			service = service.replace("'","")
			currentIndex = endIndex+1
			#get message text
			text = tempVal[currentIndex:]
			text = text[1:-2]
			#print(tempVal)
			#print(is_from_me,service,text)
			output.append({"is_from_me":is_from_me, "service":service, "text":text})
		output.reverse()
		KeyboardSocketHandler.send_updates({"type":"thread","data":output})
	releaseList = []
	pressList = []
	
	class Application(tornado.web.Application):
		def __init__(self):
			handlers = [(r"/keyboardSocket", KeyboardSocketHandler),(r".*", MainHandler)]
			super(Application, self).__init__(handlers)


	class MainHandler(tornado.web.RequestHandler):
		def get(self):
			global closeThreads
			if closeThreads:
				sys.exit()
			fileName = self.request.path
			if fileName == "/":
				fileName = "/index.html"
			contentType = ""
			if ".html" in fileName:
				contentType = 'text/html'
			if ".css" in fileName:
				contentType = 'text/css'
			if ".json" in fileName:
				contentType = 'application/json'
			if ".ico" in fileName:
				contentType = "image/x-icon"

			with open('.'+fileName, 'rb') as f:
				self.set_header('Content-Type', contentType)
				self.write(f.read())
		def post(self):
			global currentThreadID
			print("successful post")
			updateSide()
			if currentThreadID != -1:
				updateMessageThread(currentThreadID)
			toaster.show_toast("Iphone Message","you triggered a refresh")


	class KeyboardSocketHandler(tornado.websocket.WebSocketHandler):
		waiters = set()
		ws_connection = None
		def open(self):
			KeyboardSocketHandler.waiters.add(self)

		def on_close(self):
			KeyboardSocketHandler.waiters.remove(self)

		def on_message(self, message):
			message = message.split(",")
			if message[0] == "side":
				updateSide()
			if message[0] =="thread":
				updateMessageThread(message[1])
			if message[0] =="send":
				global ssh
				command = 'clsms "'+message[2]+'" '+message[1] 
				ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
				#updateMessageThread(message[1])


		@classmethod
		def send_updates(cls, keypress):
			print("we received the send")
			for waiter in cls.waiters:
				try:
					waiter.write_message(keypress)
				except:
					''''''
	recorded = []
	def print_pressed_keys(e):
		if e.event_type == "down":
			if e.scan_code in recorded:
				return
			else:
				recorded.append(e.scan_code)
				packet = {'type':"press",'scan_code':e.scan_code,'value':e.name}
				asyncio.set_event_loop(asyncio.new_event_loop())
				KeyboardSocketHandler.send_updates(packet)
		else:
			if e.scan_code in recorded:
				del recorded[recorded.index(e.scan_code)]
			packet = {'type':"release",'scan_code':e.scan_code,'value':e.name}
			KeyboardSocketHandler.send_updates(packet)

	def main():
		tornado.options.parse_command_line()
		app = Application()
		app.listen(options.port)
		tornado.ioloop.IOLoop.current().start()
		sys.exit()
	
	main()
start()