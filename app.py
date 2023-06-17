from flask import Flask, request, jsonify, render_template
import openai
import json
import yfinance as yf
import os
import datetime

openai.api_key = os.environ.get('OPENAI_API_KEY')

app = Flask(__name__)

def get_stockinfo(stock_code_all, start_date="2023-01-01", end_date=str(datetime.date.today())):
    if start_date > end_date:
        return None
    end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    end_date = end_date + datetime.timedelta(days=1) #结束日期延后一天
    end_date = end_date.strftime('%Y-%m-%d')
    
    stock_code_all = stock_code_all.split(",")
    stocklist = {}
    for stock_code in stock_code_all:
        stockinfo = {}
        if not stock_code.endswith('.HK'):
            stock_code = stock_code.strip().split('.')[0]
        if stock_code.startswith(('60', '688')):
            stock_code += '.SS'
        elif stock_code.startswith(('00', '002', '30')):
            stock_code += '.SZ'
        # 从Yahoo Finance获取股票数据
        ticker = yf.Ticker(stock_code)
        df = ticker.history(start=start_date, end=end_date)
        if len(df) == 0:
            return None
        stock_info = ticker.info
        #for key, value in stock_info.items():
        #    print(f"{key}: {value}")
        longname = stock_info["longName"]
        current_price = stock_info["currentPrice"]
        stockinfo[stock_code] = df['Close'].round(2).tolist()
        stocklist.update(stockinfo)
    print(stocklist)
    return stocklist

# Step 1, send model the user query and what functions it has access to
def run_conversation(question):
    current_date = datetime.date.today()
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0613",
        messages=[{"role": "user", "content": question}],
        temperature=0,
        functions=[
            {
                "name": "get_stockinfo",
                "description": f"今天的日期是{current_date}，根据用户输入的stock code和起止时间，获取股票价格信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stock_code": {
                            "type": "string",
                            "description": "all stock codes mentioned",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "start date",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "end date",
                        },
                    },
                    "required": ["stock_code"],
                },
            }
        ],
        function_call="auto",
    )
    
    print(f"{response['usage']}\n{response['choices'][0]['message']}")
    message = response['choices'][0]['message']
    arguments = json.loads(message["function_call"]["arguments"])

    # Step 2, check if the model wants to call a function
    if message.get("function_call"):
        function_name = message["function_call"]["name"]
        function = globals()[function_name]
        # Step 3, call the function
        # Note: the JSON response from the model may not be valid JSON
        function_response = function(*arguments.values())

        # Step 4, send model the info on the function call and function response
        second_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-0613",
            messages=[
                {"role": "user", "content": question}, # 第一 user
                message, # 第二 assistant call什么函数，参数是什么
                {
                    "role": "function", # 第三 function
                    "name": function_name,
                    "content": "起止时间内的每日股票价格：" + str(function_response) + "\n不要评价起止时间之外的数据，不要列出所有股价，除非用户要求", # 函数返回
                },
            ],
        )
        print(f"{second_response['usage']}\n")
        return second_response["choices"][0]["message"]['content']

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chatbot():
    data = request.get_json()
    question = data['question']
    response = run_conversation(question)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
