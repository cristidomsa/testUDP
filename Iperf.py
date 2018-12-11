import os
import re
import csv
import time
import shlex
import logging
import argparse
import datetime
import sys
import xml.etree.cElementTree as etree
from subprocess import Popen, PIPE
from time import sleep

__name__ = 'TestUDP'

sys.tracebacklimit = 0

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger(__name__)

def testFail(params):

    if params['TestName'] == 'Throughput':
        if float(params['Throughput']) < float(params['Criteria']):
            return True
            
    if params['TestName'] == 'PacketLossRate':
        if float(params['LostTotalDatagramsPerc']) > float(params['Criteria']):
            return True

    if params['TestName'] == 'BandwidthUtilization':
        if float(params['BandwidthUtilization']) < float(params['Criteria']):
            return True
    
    if params['TestName'] == 'Jitter':
        if float(params['Jitter']) > float(params['Criteria']):
            return True
    
    if params['TestName'] == 'E2EDelay':
        if params['AvgRTT'] == 'N/A' or float(params['AvgRTT']) > float(params['Criteria']):
            return True

def makePingReport(content):
    
    result = {}

    regex_info = r"SENT.+to\s(\d+\.\d+\.\d+\.\d+):(\d+)"
    regex = r"Max rtt: (\S+) .* Min rtt: (\S+) .* Avg rtt: (\S+)"
    for _, match in enumerate(re.finditer(regex, content, re.MULTILINE)):
        result['MaxRTT'] = match.groups()[0]
        result['MinRTT'] = match.groups()[1]
        result['AvgRTT'] = match.groups()[2]
    
    for _, match in enumerate(re.finditer(regex_info, content, re.MULTILINE)):
        result['DestIP'] = match.groups()[0]
        result['DestPort'] = match.groups()[1]

    return result


def makeReport(listString):
    # Gathering all parameteres from result returned by iperf
    # Define dictionary for result
    resultDict={}
    
    flag1 = True
    flag2 = True
    # Iterate over iperf's strings and find all neccesary information
    try:
        for index, line in enumerate(listString,0):
            #print(line)
            lexem = line.split()
            if flag1 and 'local' in line and 'port' in line and 'connected with' in line:
                resultDict['Localhost']  = lexem[3]
                resultDict['Localport']  = lexem[5]
                resultDict['Remotehost'] = lexem[8]
                resultDict['Remoteport'] = lexem[10]
                flag1 = False
                continue
            if 'ID' in line:
                lexem = listString[index+1].split()
                resultDict['Bandwidth'] = lexem[6]
                resultDict['BandwidthMeasurement'] = lexem[7]
                
            if flag2 and 'Server Report:' in line :
                #print('>>',listString[index+1])
                lexem = listString[index+1].split()
                resultDict['Interval']  = lexem[2].split('-')[1]
                resultDict['IntervalMeasurement']  = lexem[3]
                resultDict['Transfer']  = lexem[4]
                resultDict['TransferMeasurement']  = lexem[5]
                resultDict['Throughput']  = lexem[6]
                resultDict['ThroughputMeasurement']  = lexem[7]
                resultDict['Jitter']  = lexem[8]
                resultDict['JitterMeasurement']  = lexem[9]
                regex = ur"(\d+\/\s*\d+)"
                matches = re.finditer(regex, listString[index+1], re.MULTILINE)
                for _, match in enumerate(matches):
                    resultDict['LostDatagrams']  = match.groups()[0].split('/')[0]
                    resultDict['TotalDatagrams']  = match.groups()[0].split('/')[1].strip()

                resultDict['LostTotalDatagramsPerc']  = float(resultDict['LostDatagrams']) / float(resultDict['TotalDatagrams']) * 100
                resultDict['BandwidthUtilization'] = float(resultDict['Transfer']) / (float(resultDict['Bandwidth']) * float(resultDict['Interval'])) * 100
                flag2 = False
                continue
    except Exception as exc:
        logger.error('Error occured during gathering data (output corrupt)', exc_info=True)
        return {}

    return  resultDict

def writeCSV(result, status):

    # Set output file name YYMMDD-HHMMSS-<test name>.csv
    resultcsvfile = time.strftime("%Y%m%d-%H%M%S") + '-' + result['TestName'] + '_' + status + '.csv'
    # Open file and write result dictionary inti file
    if result['TestName'] == 'E2EDelay':
        header = ['DestIP', 'DestPort', 'MaxRTT','MinRTT','AvgRTT']
    else:
        header = [
        'TestName',
        'Localhost',
        'Localport',
        'Remotehost',
        'Remoteport',
        'Transfer',
        'TransferMeasurement',
        'Bandwidth',
        'BandwidthMeasurement',
        'BandwidthUtilization',
        'Throughput',
        'ThroughputMeasurement',
        'Interval',
        'IntervalMeasurement',
        'Jitter',
        'JitterMeasurement',
        'LostDatagrams',
        'TotalDatagrams',
        'LostTotalDatagramsPerc',
        ]

    with open(resultcsvfile, 'w+') as csvoutputfile:
        writer = csv.writer(csvoutputfile, delimiter=',')
        writer.writerow(header)
        writer.writerow([result[col] for col in header])

def runTest(baserun, test, timeout):
    try:
        run = []
        # Split coomand line to list.Required by Popen
        args = shlex.split(baserun)
        # Save result list to list 'run'
        run.extend(args)
        #Convert tags from XML section for current test into command line parameteres for iperf
        # Add it to list 'run' too
        for command in test:
            run.append('-' + command.tag)

            if command.text and re.sub('\s+', '', command.text):
                run.append(command.text)

        if test.tag == 'E2EDelay':
            run[0] = 'nping'
        
        # Execute test. Coomand line is defined in list 'run'
        p = Popen(run, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        # Get stdout and stdout from process with timeout

        output = None
        for t in xrange(int(timeout)):
            sleep(1)
            if p.poll() is not None:
                output, err = p.communicate()
                break
        
        if output is None:
            p.kill()
            logger.error('Timeout exceded!')
            raise Exception('TimeoutExceded')

        rc = p.returncode
        # Write all to log
        if rc == 0:
            logger.info('*'*12 + 'OUTPUT' + '*'*15)
            logger.info('\n' + output)
            logger.info('*'*11 + 'END OUTPUT' + '*'*12)
            logger.info('-'*12)
        else:
            logger.info('*'*12 + 'OUTPUT' + '*'*15)
            logger.error(output)
            logger.error(err)
            logger.info('*'*11 + 'END OUTPUT' + '*'*12)
            logger.info('-'*12)

        # Gather all neccesary information from text output
        if test.tag == 'E2EDelay':
            result = makePingReport(output)
        else:
            result = makeReport(str(output).split('\n'))


    except Exception as exc:
        logger.error('Error occured during test', exc_info=True)
        return {}

    # Return result
    return  result


# Define comand line parameters
# -x/--xml Mandatory parameter. Path to input xml file
# -t/--test Not required parameter. Define which test section from XML-file will be executed
#           Default- All sections

parser = argparse.ArgumentParser(description='Iperf client wrapper')
parser.add_argument('-x', '--xml', help='Path to xml config file', required=True)
parser.add_argument('-t', '--test', help='Test to run from xml config file', default='all')

# Set logger parameteres
# - output messages to console
#   and
# - write message to log-file

logger.setLevel(logging.DEBUG)
console_log = logging.StreamHandler()
file_log = logging.FileHandler(os.path.join(SCRIPT_DIR,'app.log'))


console_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log.setFormatter(console_format)
file_log.setFormatter(file_format)

logger.addHandler(console_log)
logger.addHandler(file_log)

ar = parser.parse_args()

logger.info('='*40)
logger.info('Start process ' + str(datetime.datetime.utcnow()))

# Open input XML-file (if exist)
if os.path.exists(ar.xml):
    with  open(ar.xml, 'r') as inpfile:
        # read content of xml file as text
        rawcontent = inpfile.read()
        try:
            # Convert text content to XML tree
            xml = etree.fromstring(rawcontent)
            # Get attribute 'run'  from iperf run="iperf">
            baserun = xml.get('run',None)
            # If attribute doesn't find, exit from script
            if not baserun:
                logger.ERROR("Parameter 'run' doesn't set ")
                raise SystemExit

            # Get attribute 'timeout'  from iperf timeout="50">
            timeout = xml.get('timeout',50)
            # If attribute doesn't find, exit from script
            if not timeout:
                logger.ERROR("Parameter 'timeout' doesn't set ")
                raise SystemExit

            # Justify xml for writing to log-file (add indents , etc ..)
            pretty_xml_as_string = etree.tostring(xml, encoding='utf-8').decode('utf-8')
            # logger.debug('Input XML:\n' + pretty_xml_as_string)
            # If will be executed all test
            if ar.test == 'all':
                logger.info('Perform all tests ..')
                # Iterate over section of XML-file
                for  index, test in enumerate(xml,1):
                    logger.info('Try to execute test {}'.format(test.get('name','NONAME')))
                    # Get attribute 'criteria'  from iperf criteria="50">
                    criteria = test.get('criteria',None)

                    if not criteria:
                        logger.warning("Parameter 'criteria' not set. Failure will not be evaluated. ")

                    # Run test for current section (stored to variable test)
                    # Result: dictionary with results returned from iperf
                    result = runTest(baserun, test, timeout)

                    if result:
                        
                        result['TestName'] = test.tag
                        
                        # write result to CSV-file
                        if criteria: 
                            result['Criteria'] = criteria
                            if testFail(result):
                                logger.warning('RESULT - {}: FAILED (criteria)'.format(test.tag))
                                writeCSV(result, status='FAIL')
                            else:
                                writeCSV(result, status='PASS')
                                logger.info('RESULT - {}: PASSED'.format(test.tag))
                            
                        else:
                            logger.info('RESULT - {}: PASSED (no criteria)'.format(test.tag))
                            writeCSV(result, status='PASS')
                    
                    else:
                        logger.warning('RESULT - {}: FAILED (timeout/no data)'.format(test.tag))
                    
                    print('*'*50)
                    print('-'*50)
                    print('*'*50)
                       
            else:
                # Defined parameter --test in command line
                # Will be executed only one test
                logger.info('Try to perform test {}'.format(ar.test))
                # Try to find the test in XML
                test = xml.find(ar.test)
                # If succesfully found , run test
                # Get attribute 'criteria'  from iperf criteria="50">
                criteria = test.get('criteria',None)

                if not criteria:
                    logger.warning("Parameter 'criteria' not set. Failure will not be evaluated. ")
                if not test is None:
                    # Run test for current section (stored to variable test)
                    # Result: dictionary with results returned from iperf
                    result = runTest(baserun, test, timeout)
                    if result:
                        # write result to CSV-file
                        result['TestName'] = test.tag
                        
                        # write result to CSV-file
                        if criteria: 
                            result['Criteria'] = criteria
                            if testFail(result):
                                logger.warning('RESULT - {}: FAILED (criteria)'.format(test.tag))
                                writeCSV(result, status='FAIL')
                            else:
                                logger.info('RESULT - {}: PASSED')
                                writeCSV(result, status='PASS'.format(test.tag))
                        else:
                            logger.info('RESULT - {}: PASSED (no criteria)')
                            writeCSV(result, status='PASS')
                    
                    else:
                        logger.warning('RESULT - {}: FAILED (timeout/no data)'.format(test.tag))
                        
                    print('*'*50)
                    print('-'*50)
                    print('*'*50)

                        
                else:
                    logger.error('Test {} not found in XML file {}'.format(ar.test, ar.xml))
        except Exception as exc:
            logger.error('Error occured during processing', exc_info=True)
else:
    logger.error("Input file {} doesn't exists".format(ar.xml))


logger.info('Finish process:' +  str(datetime.datetime.utcnow()))
logger.info('='*41)