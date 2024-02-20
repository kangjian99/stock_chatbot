from flask import Flask, request, jsonify, render_template, Response
from openai import OpenAI
import json, os, datetime
import yfinance as yf
#from dotenv import load_dotenv
#load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
model = "gpt-3.5-turbo-0125"
model4 = "gpt-4-0125-preview"

client = OpenAI(
  api_key = API_KEY, 
)

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
        #stock_info = ticker.info
        #longname = stock_info["longName"]
        #current_price = stock_info["currentPrice"]
        stockinfo[stock_code] = df['Close'].round(2).tolist()
        stocklist.update(stockinfo)
    print(stocklist)
    return stocklist

# Step 1, send model the user query and what functions it has access to
def run_conversation(question):
    if '股价' not in question:
        question += '(股价)' # 防止response发散
    current_date = datetime.date.today()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        temperature=0,
        functions=[
            {
                "name": "get_stockinfo",
                "description": f"今天的日期是{current_date}，你的任务是根据用户输入的信息提取所有的stock code以及起止时间(如果起止时间未提供也不要询问用户)，并获取对应时间段的股票价格信息",
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
    
    print(f"第一次调用：{response.usage}\n{response.choices[0].message}")
    message = response.choices[0].message
    arguments = json.loads(message.function_call.arguments)

    # Step 2, check if the model wants to call a function
    if message.function_call:
        function_name = message.function_call.name
        function = globals()[function_name]
        # Step 3, call the function
        # Note: the JSON response from the model may not be valid JSON
        function_response = function(*arguments.values())

        # Step 4, send model the info on the function call and function response
        second_response = client.chat.completions.create(
            model=model,
            stream=True,
            messages=[
                {"role": "user", "content": question}, # 第一 user
                message, # 第二 assistant call什么函数，参数是什么
                {
                    "role": "function", # 第三 function
                    "name": function_name,
                    "content": "起止时间内的每日股票价格：" + str(function_response) + "\n你是一位资深分析师，擅长分析股价数据并从中得出结论，列出代表性的股价信息，列出至少三条分析结论，并给用户具体的投资建议。不要只用几句话应付用户，不要评价起止时间之外的数据，无需列出所有股价除非用户要求", # 函数返回
                },
            ],
        )
        # print(f"第二次调用：{second_response.usage}\n")
        return second_response

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chatbot():
    data = request.get_json()
    question = data['question']
    def generate(question):
        response = run_conversation(question)
        partial_words = ""
        for chunk in response:
            if chunk:
                try:
                    if chunk.choices[0].delta:
                       finish_reason = chunk.choices[0].finish_reason
                       if finish_reason == "stop":
                           break
                       if chunk.choices[0].delta.content:
                           partial_words += chunk.choices[0].delta.content
                           yield json.dumps({'content': partial_words}).encode('utf-8')
                except json.JSONDecodeError:
                    pass
        # yield jsonify({'content': partial_words})  # 保证最后一个部分被返回

    return Response(generate(question), mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=True)