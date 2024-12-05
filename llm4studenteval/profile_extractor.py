import pdfplumber
import re
from tqdm import tqdm
import os
import json

from utils import vlm_completion, baidu_table_ocr, baidu_text_ocr, table_ocr_result_to_markdown
from prompts import page_classification_prompt_v4 as page_classification_prompt

def findnth(haystack, needle, n):
    parts= haystack.split(needle, n+1)
    if len(parts)<=n+1:
        return -1
    return len(haystack)-len(parts[-1])-len(needle)

def transform_award(profile):
    award_list_text = profile.split("Award Name / Title")
    award_list = []
    for i, award_text in enumerate(award_list_text[1:]):
        award = {}
        award["Title"] = award_text.split("\n")[0]
        award["Description"] = award_text.split("Details of the Award")[1].split("Basis of Award")[0]
        award_list.append(award)
    return award_list

def transform_work(profile):
    # print(profile)
    work_list_text = profile.split("Type")
    work_list = []
    for i, award_text in enumerate(work_list_text[1:]):
        award = {}
        if "Position Held /" in award_text:
            position=award_text.split("Position Held /")[1].split("\n")[0]
        else:
            position="MISSINGPOS"
            print("Position keyword missing")

        if "Period" in award_text:
            duration=award_text.split("Period")[1].split("\n")[0]
        else:
            duration="MISSINGDURATION"
            print("Duration keyword missing")

        if "Job Duties / Training Areas" in award_text:
            description=award_text.split("Job Duties / Training Areas")[1]
        else:
            description="MISSINGDESCRIPTION"
            print("Description keyword missing")

        if "Name of Organization" in award_text:
            organization=award_text.split("Name of Organization")[1].split("Country / Region")[0]
        else:
            organization="MISSINGORGANIZATION"
            print("Organization keyword missing")

        award["Title"] = position + " " + award_text.split("\n")[0] + " in " + organization
        award["Duration"] = duration
        award["Description"] = description
        work_list.append(award)
    return work_list


def extract_student_profile(pdf_path):

    section_titles = [
        "Public Examination Results",
        "English Language Proficiency",
        "Awards and Professional Qualifications",
        "Extracurricular Activities / Volunteer Work",
        "Work Experience / Internship / Training",
        "Publications",
        "Proposed Research Plan / Vision Statement",
        "Additional Information",
        "Supporting Documents",
        "/ CV",
        # "Reference Report",
    ]
    #possible keyword in CV, all should be written in lower case
    CV_tiles=[
        "cv",
        "curriculum vitae",
        "resume",
    ]

    sections_content = {title: "" for title in section_titles}
    sections_content["Education Background"] = {}
    extracted_text = []
    read_transcript_start_page = 9999999999
    classify_transcript_start_flag = False
    classify_transcript_end_flag = False
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if i == 0:
                # identity = (page.extract_table()[0][1].split("\n")[0], pdf_path.split("_")[0].split("-")[-1])
                # identity = (page.extract_table()[0][1].split("\n")[0], pdf_path.split("\\")[-1][:11])
                # identity = (page.extract_table()[0][1].split("\n")[0], pdf_path.split("/")[-1].replace('.pdf',''))
                identity = (' '.join(re.sub('[\d/]','',page.extract_table()[0][1].split("\n")[0]).split()), pdf_path.split("/")[-1].replace('.pdf',''))
                # print(page.extract_table()[3])
                date_of_birth = page.extract_table()[3][1]
            elif i == 1 or i == 2:
                try:
                    add_text = ""
                    education_text = page.extract_text().split("Education Background")[1]
                    if "Public Examination" not in education_text:
                        add_text = pdf.pages[i+1].extract_text().split("Public Examination")[0]
                    education_text += add_text
                except:
                    pass

            elif ("Submit and Pay" in page_text):
                read_transcript_start_page = i+2

            if read_transcript_start_page <= i <= 70 and not classify_transcript_end_flag:
                trans_image = pdf.pages[i].to_image(resolution=200).original
                classification_response = vlm_completion(img=trans_image, text_prompt=page_classification_prompt)
                if 'yes' in classification_response.lower():
                    classify_transcript_start_flag = True
                    ocr_status, ocr_result =  baidu_table_ocr(trans_image)
                    if ocr_status:
                        transcript_text = table_ocr_result_to_markdown(ocr_result)
                    else:
                        transcript_text = baidu_text_ocr(trans_image)
                        
                    extracted_text.append(transcript_text)
                else:
                    if classify_transcript_start_flag:
                        classify_transcript_end_flag = True
                    else:
                        pass

        sections_content["ID"] = {"identity": identity, "date_of_birth": date_of_birth}
        sections_content["Education Background"] = education_text
        sections_content["Taken Courses"] = extracted_text

    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text()
                full_text += text + "\n\n"
            except:
                print(f"cannot read page {i}")
                continue


    # List of keywords to search for each category. These would need to be adjusted for different formats.
    for title in section_titles:
        # Find the start of the section by title

        if title == "/ CV":
            #find the text in Supporting Documents - Other documents
            otherDocumentText=full_text.split("II. Other documents")[1].split("Payment and Submission")[0]
            otherDocumentTextLower=otherDocumentText.lower()
            startCVPattern=r'\n\d+ ' #the pattern before cv's name, usually \n+series of number+" ", like "\n123 "
            endCVPattern=r' \d{2}/\d{2}/\d{4}' #the pattern after cv's name, usually dd/mm/yyyy, like "27/06/2023"
            cvRealTitle=None

            #Find the cv real title
            for cvTitle in CV_tiles:
                if cvTitle in otherDocumentTextLower:
                    CVKeywardIDX=otherDocumentTextLower.find(cvTitle)+len(cvTitle)
                    # seperate the line before and after the keyword
                    cvTitleLineBefore=otherDocumentTextLower[:CVKeywardIDX]
                    cvTitleLineAfter=otherDocumentTextLower[CVKeywardIDX:]

                    #find the keyword before and after CV's title
                    startCVTitle=re.findall(startCVPattern,cvTitleLineBefore)
                    endCVTitle=re.findall(endCVPattern,cvTitleLineAfter)

                    #index of CV title
                    if len(startCVTitle) == 0:
                        continue
                    else:
                        startCVTitleIDX=cvTitleLineBefore.rfind(startCVTitle[-1])+len(startCVTitle[-1])

                    if len(endCVTitle) == 0:
                        continue
                    else:
                        endCVTitleIDX=CVKeywardIDX+cvTitleLineAfter.find(endCVTitle[0])

                    cvRealTitle=otherDocumentText[startCVTitleIDX:endCVTitleIDX]
                    break #only find the first cv name

            if cvRealTitle != None:
                start_idx = findnth(full_text, f"{identity[0].replace(' ', ', ',1)} / {cvRealTitle}", 0)
            else:
                start_idx=-1
        else:
            start_idx = full_text.find(title)

        # If the title is not found, continue to the next title
        if start_idx == -1:
            continue
        # Find the end of the section, which is either the start of the next section or the end of the document
        if title == "/ CV":
            #temp_idx is the end of the title
            temp_idx = start_idx+len(f"{identity[0].replace(' ', ', ', 1)} / {cvRealTitle}")

            #Get all CV pages
            while full_text[temp_idx:].find(f"{identity[0].replace(' ', ', ', 1)} / {cvRealTitle}") != -1:
                temp_idx=temp_idx+full_text[temp_idx:].find(f"{identity[0].replace(' ', ', ', 1)} / {cvRealTitle}")+len(f"{identity[0].replace(' ', ', ', 1)} / {cvRealTitle}")

            #Only get 1 CV pages
            # while findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ', 1)} / {cvRealTitle}", 0) == -1: #Only replace the first space. The format is Last name, First name
            #     temp_idx = findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ',1)} / {cvRealTitle}", 0)

            end_idx = min([full_text.find(f"/ {identity[1]}", temp_idx + 1)] + [len(full_text)])
        else:
            end_idx = min([full_text.find(t, start_idx + 1) for t in section_titles if full_text.find(t, start_idx + 1) != -1] + [len(full_text)])
        # Extract the content for this section
        sections_content[title] = full_text[start_idx:end_idx].strip()

    sections_content["Awards and Professional Qualifications"] = transform_award(sections_content["Awards and Professional Qualifications"])
    sections_content["Work Experience / Internship / Training"] = transform_work(sections_content["Work Experience / Internship / Training"])
    important_keys = ["ID", "Education Background", "Awards and Professional Qualifications",
                    "Publications", "English Language Proficiency", "Proposed Research Plan / Vision Statement",
                    "/ CV", "Extracurricular Activities / Volunteer Work", "Taken Courses"]
    filtered_profile = {key: sections_content[key] for key in important_keys}

    #if the CV doesn't exist, it will be replaced by "Work Experience / Internship / Training"
    if filtered_profile["/ CV"] == "":
        filtered_profile["/ CV"]=sections_content["Work Experience / Internship / Training"]
    return filtered_profile


def extract_student_profile_25(pdf_path):

    section_titles = [
        "Public Examination Results",
        "English Language Proficiency",
        "Awards and Professional Qualifications",
        "Extracurricular Activities / Volunteer Work",
        "Work Experience / Internship / Training",
        "Publications",
        "Proposed Research Plan and Past Research Experience",
        "Additional Information",
        "Upload Supporting Documents",
        "CV",
        # "Reference Report",
    ]
    sections_content = {title: "" for title in section_titles}
    sections_content["Education Background"] = {}
    extracted_text = []
    read_transcript_flag = 0
    possible_payment_start_page = 8

    read_transcript_start_page = 9999999999
    classify_transcript_start_flag = False
    classify_transcript_end_flag = False
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[0:1]+pdf.pages[2:3]+pdf.pages[possible_payment_start_page:possible_payment_start_page+20]):
            if i == 0:
                pattern1 = re.compile('..(?=' + '/ 40' + ')')
                pattern2 = re.compile('..(?=' + '/ 30' + ')')
                # identity = (page.extract_table()[0][1].split("\n")[0].replace(' 5 / 40', '').replace('6 / 30', ''), pdf_path.split("/")[-1].split(".")[0])
                identity = (re.sub(pattern2, '', re.sub(pattern1, '', page.extract_table()[0][1].split("\n")[0], count = 1).replace('/ 40', ''), count = 1).replace('/ 30', ''), pdf_path.split("/")[-1].split(".")[0])
                # print(identity)
                # print(pdf_path.split("_")[0].split("-")[-1])
                date_of_birth = page.extract_table()[3][1]
            elif i == 1:
                add_text = ""
                education_text = page.extract_text().split("Education Background")[1]
                edu_page = 2
                while("Public Examination" not in pdf.pages[edu_page+1].extract_text()):
                    edu_page+=1
                    add_text = pdf.pages[edu_page].extract_text()
                    # print(f"{edu_page}:{add_text}")
                    education_text += add_text
                education_text += pdf.pages[edu_page+1].extract_text().split("Public Examination")[0]
                # print(education_text)
            elif ("Submit and Pay" in page.extract_text()):
                read_transcript_start_page = i+2

            if read_transcript_start_page <= i <= 70 and not classify_transcript_end_flag:
                trans_image = pdf.pages[i].to_image(resolution=200).original
                classification_response = vlm_completion(img=trans_image, text_prompt=page_classification_prompt)
                if 'yes' in classification_response.lower():
                    classify_transcript_start_flag = True
                    ocr_status, ocr_result =  baidu_table_ocr(trans_image)
                    if ocr_status:
                        transcript_text = table_ocr_result_to_markdown(ocr_result)
                    else:
                        transcript_text = baidu_text_ocr(trans_image)
                        
                    extracted_text.append(transcript_text)
                else:
                    if classify_transcript_start_flag:
                        classify_transcript_end_flag = True
                    else:
                        pass
                    # print(transcript_text)
                    # extracted_text.append(transcript_text)
            # if "Official transcript" in page.extract_text()[:100]:
            #     print(f"page: {i} is official transcript")
        sections_content["ID"] = {"identity": identity, "date_of_birth": date_of_birth}
        sections_content["Education Background"] = education_text
        sections_content["Taken Courses"] = extracted_text
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text()
                full_text += text + "\n\n"
            except:
                print(f"cannot read page {i}")
                continue
            
    
    # List of keywords to search for each category. These would need to be adjusted for different formats.
    
    for title in section_titles:
        # Find the start of the section by title
    
        if title == "CV":
            other_name_flag = 0
            start_idx = findnth(full_text, f"{identity[0].replace(' ', ', ')} / CV", 0)
            # print(start_idx)
            if start_idx == -1:
                other_name_flag = 1
                start_idx = findnth(full_text, f"{identity[0].replace(' ', ', ')} / Curriculum Vitae", 0)
                # print(start_idx)
        else:
            start_idx = full_text.find(title)
            # print(title)
            # print(start_idx)
    
        # If the title is not found, continue to the next title

        if start_idx == -1:
            continue
        # Find the end of the section, which is either the start of the next section or the end of the document
        if title == "CV":
            temp_idx = start_idx
            if other_name_flag == 1:
                while findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ')} / Curriculum Vitae", 0) == -1:
                    temp_idx = findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ')} / Curriculum Vitae", 0)
            else:
                while findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ')} / CV", 0) == -1:
                    temp_idx = findnth(full_text[temp_idx:], f"{identity[0].replace(' ', ', ')} / CV", 0)
            end_idx = min([full_text.find(f"/ {identity[1]}", temp_idx + 1)] + [len(full_text)])
        
        else:
            end_idx = min([full_text.find(t, start_idx + 2) for t in [title0 for title0 in section_titles if title0!=title] if full_text.find(t, start_idx + 2)!=-1]+[len(full_text)])
            # end_idx = min([full_text.find(t, start_idx + 1) for t in section_titles if full_text.find(t, start_idx + 1) != -1] + [len(full_text)])
        # print(title)
        # print(end_idx)
        # Extract the content for this section
        sections_content[title] = full_text[start_idx:end_idx].strip()
        
    sections_content["Awards and Professional Qualifications"] = transform_award(sections_content["Awards and Professional Qualifications"])
    sections_content["Work Experience / Internship / Training"] = transform_work(sections_content["Work Experience / Internship / Training"])
    important_keys = ["ID", "Education Background", "Awards and Professional Qualifications", "Work Experience / Internship / Training",
                    "Publications", "English Language Proficiency", "Proposed Research Plan and Past Research Experience", 
                    "CV", "Extracurricular Activities / Volunteer Work", "Taken Courses"]
    filtered_profile = {key: sections_content[key] for key in important_keys}
    # print(sections_content["Taken Courses"])
    
    return filtered_profile

def read_profiles_from_folder(folder_path):
    # Iterate through all files in the specified folder
    read_file_list = []
    for filename in tqdm(os.listdir(folder_path)):
        # Construct absolute path to file
        file_path = os.path.join(folder_path, filename)

        # Check if the current path is a file and not a directory
        if os.path.isfile(file_path) and ".pdf" in file_path:
            print(f"Found file: {filename}")
            profile = extract_student_profile(file_path)
            profile["Proposed Research Plan / Vision Statement"] = profile["Proposed Research Plan / Vision Statement"][:5000]
            if len(json.dumps(profile)) > 20000:
                print(f"warning: {filename}, string len: {len(json.dumps(profile))}")
            read_file_list.append(profile)

    return read_file_list