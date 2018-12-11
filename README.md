Server:

    iperf -s

    iperf -s -u -l 32k -w 128k -i 1

Client:

Run all tests:
    
    python Iperf.py -x file.xml

Run one category test (Jitter)
    
    python Iperf.py -x file.xml -t Jitter


Iperf Doc:
https://iperf.fr/iperf-doc.php

Nping Doc:
https://nmap.org/book/nping-man.html
