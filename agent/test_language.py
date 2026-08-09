import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.dialogue import detect_language

print(detect_language("mera bête ko computer science mein interest hai"))  # expect: hi
print(detect_language("I want to know about CSE admission"))               # expect: en
print(detect_language("मेरा बेटा CSE में interested hai"))                    # expect: hi
print(detect_language("What is the fee structure"))                        # expect: en