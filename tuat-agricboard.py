import os
from requests_oauthlib import OAuth1Session
import requests
from bs4 import BeautifulSoup
import lxml
import re
import json
import redis
import time

#ツイッターの認証情報。事前に環境変数に読み込ませる
CK = os.environ['CONSUMER_KEY']
CS = os.environ['CONSUMER_SECRET']
AT = os.environ['ACCESS_TOKEN']
ATS = os.environ['ACCESS_TOKEN_SECRET']
twitter = OAuth1Session(CK, CS, AT, ATS)

#ツイート用エンドポイント
url = "https://api.twitter.com/1.1/statuses/update.json"

#botのユーザー名
username = "@tuat_agricboard "

def main():
    global res
    new_ilist = []
    new_dlist = []
    #学生生活、教務を１０件ずつとってきて、id, dateをそれぞれnewリストに追加
    for num in range(2):
        resp = requests.get("http://t-board.office.tuat.ac.jp/A/boar/resAjax.php", params={'bAnno': num, 'par': 10})
        soup = BeautifulSoup(resp.text, 'lxml')
        new_ilist.extend([tr.get('i') for tr in soup.find_all('tr', {'class': "row"})])
        new_dlist.extend([p.get_text()[:5] for p in soup.find_all('p', {'class': ""})])

    old_ilist = r.keys()
    old_dlist = [r.get(i) for i in old_ilist]

    #更新されてなかったらプログラムをまたスリープ
    if old_ilist == new_ilist and old_dlist == new_ilist:
        return
    else:
        #データベースを更新しとく
        r.flushdb()
        for i, d in zip(new_ilist, new_dlist):
            r.set(i,d)

        for i, d in zip(new_ilist, new_dlist):
            #前回のリストとかぶってないかチェック
            if not i in old_ilist or (i in old_ilist and d != old_dlist[old_ilist.index(i)]):
                #get_contents関数に投げるとタイトル、対象者、コンテンツ、リンクと添付ファイルを返してくれる
                title, target, content, links, attach = get_contents(i)
                #括弧などを除いたタイトルが英語か確認
                title_ = re.sub('[！？（）［］｢｣「」【】]', '', title)
                title = "【" + title + "】"
                #タイトルと対象者を連結し、ツイート
                title_target = title + '\n' + target
                res = twitter.post(url, params = {"status" : title_target})
                jsoned = json.loads(res.text)
                #本文全体が英語のとき、文字数制限が倍になるためlimitationを大きくする
                if not re.compile('[\u0000-\u007F]+').fullmatch(title_):#日本語を含む時
                    limitation = 130
                else:#日本語を含まない時
                    limitation = 270
                #リプライに必要なツイート数の計算
                reply_counts = len(content) // limitation + 1
                for a in range(reply_counts):
                    #contentを分割、自身のユーザー名と共にhonbunに代入し、ツイート
                    honbun = username + content[a * limitation:(a + 1) * limitation]
                    res = twitter.post(url, params = {"status" : honbun, "in_reply_to_status_id": jsoned["id_str"]})
                    jsoned = json.loads(res.text)
                #リンク、添付ファイルがあるか確認し、あれば一つづつリプライ
                if links != None:
                    for l in links:
                        #リンクの文字列が//から始まってた場合削除しhrefに代入
                        href = l.get("href")[2:] if l.get("href")[:2] == "//" else l.get("href")
                        #linkに自身のユーザー名と添付ファイル名、ファイルのアドレスを代入し、ツイート
                        link = username + l.get_text() + "\n" + href
                        res = twitter.post(url, params = {"status" : link, "in_reply_to_status_id": jsoned["id_str"]})
                        jsoned = json.loads(res.text)
                if attach != None:
                    for a in attach:
                        #tenpuに自身のユーザー名と添付ファイル名、ファイルのアドレスを代入し、ツイート
                        tenpu = username + a.get_text() + "\nhttp://t-board.office.tuat.ac.jp" + a.get("href")
                        res = twitter.post(url, params = {"status" : tenpu, "in_reply_to_status_id": jsoned["id_str"]})
                        jsoned = json.loads(res.text)

        return

def get_contents(i):
    #soupにお知らせ内容のページ情報を代入
    resp = requests.get("http://t-board.office.tuat.ac.jp/A/boar/vewAjax.php", params={'i': i})
    soup = BeautifulSoup(resp.text, 'lxml')
    #タイトルはemphasis1クラスのtdの中身
    title = soup.find('td', {'class': 'emphasis1'}).get_text()
    #対象者はstyle属性がver~略~dle;のスパンの中身、長いものをtext_shrinkerで縮める
    target = text_shrinker(soup.find('span', {'style': 'vertical-align: middle;'}).get_text())
    #本文はemphasis2クラスのtdの中身、改行やスペースは削除
    content = soup.find('td', {'class': "emphasis2"}).get_text().replace('\n', '').replace('\t', '').replace('　', '').replace('  ', ' ').replace('  ', ' ').replace('  ', ' ')
    #urlがあればリストを、なければNoneを代入
    try:
        links = soup.find('td', {'class': "emphasis2"}).find_all('a') ## TODO: これでうまく行くか実験.get("href")
    except:
        links = None
    #添付ファイルがあればリストを、なければNoneを代入
    try:
        attach = soup.find('ul', {'id': "ATTACH-LIST"}).find_all('a') ## TODO: これでうまく行くか実験.get("href")
    except:
        attach = None
    return title, target, content, links, attach

def connect():
    return redis.from_url(
        url=os.environ.get('REDIS_URL'), # 環境変数にあるURLを渡す
        decode_responses=True, # 日本語の文字化け対策
    )
r = connect()

def text_shrinker(text):
    #原始的な手法でテキストを整形するスクリプト。
    # TODO: ==改善の余地あり==
    if text == "府中キャンパス全対象":
        return text
    else:
        try:
            text = text.replace('MP[All] / MS[All] / ML[All] / MC[All] / MR[All] / MK[All] / MN[All] / MT[All] / MI[All]', '全農学府修士過程')
        except:
            pass
        try:
            text = text.replace('MP[1年] / MS[1年] / ML[1年] / MC[1年] / MR[1年] / MK[1年] / MN[1年] / MT[1年] / MI[1年]', '農学府修士課程１年')
        except:
            pass
        try:
            text = text.replace('MP[2年] / MS[2年] / ML[2年] / MC[2年] / MR[2年] / MK[2年] / MN[2年] / MT[2年] / MI[2年]', '農学府修士課程１年')
        except:
            pass
        try:
            text = text.replace('An[All] / Bn[All] / En[All] / Rn[All] / Vn[All]', '全農学部')
        except:
            pass
        try:
            text = text.replace('An[All] / Bn[All] / En[All] / Rn[All] / Vn[1年] / Vn[2年] / Vn[3年] / Vn[4年]', '全農学部(Vn5,6年を除く)')
        except:
            pass
        try:
            text = text.replace('An[All] / Bn[All] / En[All] / Rn[All]', '全農学部(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[2年] / Bn[2年] / En[2年] / Rn[2年] / An[3年] / Bn[3年] / En[3年] / Rn[3年] / An[4年] / Bn[4年] / En[4年] / Rn[4年]', '農学部２〜４年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[3年] / Bn[3年] / En[3年] / Rn[3年] / An[4年] / Bn[4年] / En[4年] / Rn[4年]', '農学部３，４年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[2年] / Bn[2年] / En[2年] / Rn[2年] / Vn[2年] / An[3年] / Bn[3年] / En[3年] / Rn[3年] / Vn[3年] / An[4年] / Bn[4年] / En[4年] / Rn[4年] / Vn[4年] / Vn[5年] / Vn[6年]', '全農学部（１年を除く）')
        except:
            pass
        try:
            text = text.replace('An[3年] / Bn[3年] / En[3年] / Rn[3年] / Vn[3年] / An[4年] / Bn[4年] / En[4年] / Rn[4年] / Vn[4年] / Vn[5年] / Vn[6年]', '全農学部（１，２年を除く）')
        except:
            pass
        try:
            text = text.replace('An[1年] / Bn[1年] / En[1年] / Rn[1年] / Vn[1年]', '農学部１年')
        except:
            pass
        try:
            text = text.replace('An[1年] / Bn[1年] / En[1年] / Rn[1年]', '農学部１年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[2年] / Bn[2年] / En[2年] / Rn[2年] / Vn[2年]', '農学部２年')
        except:
            pass
        try:
            text = text.replace('An[2年] / Bn[2年] / En[2年] / Rn[2年]', '農学部２年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[3年] / Bn[3年] / En[3年] / Rn[3年] / Vn[3年]', '農学部３年')
        except:
            pass
        try:
            text = text.replace('An[3年] / Bn[3年] / En[3年] / Rn[3年]', '農学部３年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[4年] / Bn[4年] / En[4年] / Rn[4年] / Vn[4年]', '農学部４年')
        except:
            pass
        try:
            text = text.replace('An[4年] / Bn[4年] / En[4年] / Rn[4年]', '農学部４年(Vnを除く)')
        except:
            pass
        try:
            text = text.replace('An[1年] / An[2年] / An[3年] / An[4年]', 'An全学年')
        except:
            pass
        try:
            text = text.replace('Bn[1年] / Bn[2年] / Bn[3年] / Bn[4年]', 'Bn全学年')
        except:
            pass
        try:
            text = text.replace('En[1年] / En[2年] / En[3年] / En[4年]', 'En全学年')
        except:
            pass
        try:
            text = text.replace('Rn[1年] / Rn[2年] / Rn[3年] / Rn[4年]', 'Rn全学年')
        except:
            pass
        try:
            text = text.replace('Vn[1年] / Vn[2年] / Vn[3年] / Vn[4年] / Vn[5年] / Vn[6年]', 'Vn全学年')
        except:
            pass
        try:
            text = text.replace('An[2年] / An[3年] / An[4年]', 'An２〜４年')
        except:
            pass
        try:
            text = text.replace('Bn[2年] / Bn[3年] / Bn[4年]', 'Bn２〜４年')
        except:
            pass
        try:
            text = text.replace('En[2年] / En[3年] / En[4年]', 'En２〜４年')
        except:
            pass
        try:
            text = text.replace('Rn[2年] / Rn[3年] / Rn[4年]', 'Rn２〜４年')
        except:
            pass
        try:
            text = text.replace('Vn[2年] / Vn[3年] / Vn[4年] / Vn[5年] / Vn[6年]', 'Vn２〜６年')
        except:
            pass
        try:
            text = text.replace('An[3年] / An[4年]', 'An３，４年')
        except:
            pass
        try:
            text = text.replace('Bn[3年] / Bn[4年]', 'Bn３，４年')
        except:
            pass
        try:
            text = text.replace('En[3年] / En[4年]', 'En３，４年')
        except:
            pass
        try:
            text = text.replace('Rn[3年] / Rn[4年]', 'Rn３，４年')
        except:
            pass
        try:
            text = text.replace('Vn[3年] / Vn[4年] / Vn[5年] / Vn[6年]', 'Vn３〜６年')
        except:
            pass
        try:
            text = text.replace('Vn[4年] / Vn[5年] / Vn[6年]', 'Vn４〜６年')
        except:
            pass
        try:
            text = text.replace('Vn[5年] / Vn[6年]', 'Vn５，６年')
        except:
            pass
        return "対象：" + text

while True:
    try:
        main()
    except Exception as e:
        #エラーのときはエラー内容と返ってきたjsonをprint
        print(e)
        print(json.loads(res.text))
    finally:
        #処理終了後５分待機
        time.sleep(300)
