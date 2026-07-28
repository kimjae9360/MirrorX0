import urllib.request
import re

url = 'https://www.httrack.com/page/2/en/index.html'
html = urllib.request.urlopen(url).read().decode('utf-8')
links = re.findall(r'href="([^"]+\.zip)"', html)
print(links)
