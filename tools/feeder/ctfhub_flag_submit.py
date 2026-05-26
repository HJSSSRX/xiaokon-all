#!/usr/bin/env python3
"""Submit flags to CTFHub via CDP browser automation.

Usage:
    python ctfhub_flag_submit.py <challenge_name> <flag>

Or from Python:
    from tools.feeder.ctfhub_flag_submit import submit_flag
    submit_flag("WebsiteManger", "ctfhub{...}")
"""

import sys
import time
import io


def submit_flag(challenge_name, flag, headless=False):
    """Submit a flag for a CTFHub challenge via CDP browser.

    Args:
        challenge_name: Partial match for the challenge card title
        flag: The flag string to submit
        headless: Not yet supported (always uses existing Chrome)

    Returns:
        (success: bool, message: str)
    """
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.path.insert(0, 'D:/ai')
    from tools.feeder.spa_crawler import SpaCrawler

    c = SpaCrawler()
    c.connect('ctfhub')

    # Navigate to challenge list
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
    time.sleep(3)
    while c._recv_any(0.3):
        pass

    # Wait for SPA render
    for i in range(10):
        body = c.evaluate('document.body ? document.body.textContent.substring(0, 200) : "no body"')
        if "We're sorry" not in str(body) and "no body" not in str(body):
            break
        time.sleep(2)
        while c._recv_any(0.3):
            pass

    # Click challenge card
    click_js = (
        'var cards=document.querySelectorAll(".ant-card-hoverable");'
        'var r="not found";'
        'for(var i=0;i<cards.length;i++){'
        '  if(cards[i].textContent.indexOf("%s")>=0){cards[i].click();r="clicked";break;}'
        '}'
        'r'
    ) % challenge_name
    result = c.evaluate(click_js)
    if 'not found' in str(result):
        return (False, "Challenge '%s' not found on current page" % challenge_name)

    time.sleep(2)
    while c._recv_any(0.3):
        pass

    # Check modal is open
    modal = c.evaluate('var m=document.querySelector(".ant-modal"); m ? "open" : "NO_MODAL"')
    if 'NO_MODAL' in str(modal):
        return (False, "Modal did not open")

    # Fill flag input
    fill_js = (
        'var inputs=document.querySelectorAll(".ant-modal input");'
        'var result="no flag input";'
        'for(var i=0;i<inputs.length;i++){'
        '  var ph=inputs[i].placeholder||"";'
        '  if(ph.indexOf("Flag")>=0||ph.indexOf("flag")>=0){'
        '    var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;'
        '    setter.call(inputs[i],"%s");'
        '    var ev=new Event("input",{bubbles:true});'
        '    inputs[i].dispatchEvent(ev);'
        '    result="filled";'
        '    break;'
        '  }'
        '}'
        'result'
    ) % flag
    fill_result = c.evaluate(fill_js)
    if 'no flag input' in str(fill_result):
        return (False, "Flag input field not found in modal")

    # Click submit button
    submit_js = (
        'var btns=document.querySelectorAll(".ant-modal button");'
        'var result="no submit";'
        'for(var i=0;i<btns.length;i++){'
        '  var t=btns[i].textContent.trim();'
        '  if(t.indexOf("提交Flag")>=0){'
        '    btns[i].click();'
        '    result="clicked: "+t;'
        '    break;'
        '  }'
        '}'
        'result'
    )
    submit_result = c.evaluate(submit_js)
    if 'no submit' in str(submit_result):
        return (False, "Submit button not found")

    # Wait for feedback
    time.sleep(3)
    while c._recv_any(0.3):
        pass

    fb = c.evaluate(
        'var els=document.querySelectorAll(".ant-message-notice-content,.ant-notification-notice");'
        'var r=[];'
        'for(var i=0;i<els.length;i++){r.push(els[i].textContent.trim());}'
        'r.length>0 ? JSON.stringify(r) : "no feedback"'
    )

    if '成功' in str(fb) or '正确' in str(fb):
        return (True, str(fb))
    elif '失败' in str(fb) or '错误' in str(fb):
        return (False, str(fb))
    else:
        return (None, str(fb))  # Unknown result


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python ctfhub_flag_submit.py <challenge_name> <flag>")
        print("Example: python ctfhub_flag_submit.py WebsiteManger ctfhub{...}")
        sys.exit(1)

    name = sys.argv[1]
    flag = sys.argv[2]
    ok, msg = submit_flag(name, flag)
    print("Success: %s" % ok)
    print("Message: %s" % msg)
