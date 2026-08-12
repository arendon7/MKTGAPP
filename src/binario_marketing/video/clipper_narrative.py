from __future__ import annotations

import math
import re
from dataclasses import asdict,dataclass


@dataclass(frozen=True)
class NarrativeSegment:
    start:float
    end:float
    text:str


@dataclass(frozen=True)
class NarrativeClip:
    start:float
    end:float
    text:str
    score:float
    tone:str
    hook_score:float
    closure_score:float
    duration_fit:float
    reasons:list[str]

    @property
    def duration(self)->float:return self.end-self.start


QUESTION_WORDS=('cómo','como','por qué','porque','qué','que','cuándo','cuando','dónde','donde','why','how','what','when','where')
HOOK_WORDS=('error','errores','secreto','clave','nunca','nadie','evita','mejor','peor','problema','verdad','mito','ojo','attention','mistake','secret','never','problem')
ACTION_WORDS=('haz','prueba','mide','ajusta','guarda','comparte','comenta','empieza','aplica','define','revisa','cierra','try','measure','save','share','comment','start','apply','review')
STORY_WORDS=('cuando','entonces','después','despues','primero','luego','historia','pasó','paso','once','then','after','first','story','happened')
EDU_WORDS=('clave','paso','pasos','método','metodo','ejemplo','significa','porque','resultado','proceso','tip','tips','method','example','result','process')
CONNECTOR_STARTS=('y ','pero ','entonces ','además ','ademas ','también ','tambien ','porque ','so ','and ','but ','then ','also ','because ')


def _clean(text:str)->str:return re.sub(r'\s+',' ',text).strip()

def _valid_segments(segments)->list[NarrativeSegment]:
    rows=[]
    for row in segments:
        start=float(getattr(row,'start',row.get('start') if isinstance(row,dict) else 0));end=float(getattr(row,'end',row.get('end') if isinstance(row,dict) else 0));text=_clean(str(getattr(row,'text',row.get('text') if isinstance(row,dict) else '')))
        if start>=0 and end>start and text:rows.append(NarrativeSegment(start,end,text))
    rows.sort(key=lambda item:(item.start,item.end))
    return rows


def _hook(text:str)->tuple[float,list[str]]:
    low=text.lower();score=0.0;reasons=[]
    if '?' in text or any(low.startswith(word+' ') for word in QUESTION_WORDS):score+=2.3;reasons.append('pregunta/hook')
    hits=sum(1 for word in HOOK_WORDS if re.search(rf'\b{re.escape(word)}\b',low))
    if hits:score+=min(2.0,0.7*hits);reasons.append('lenguaje de atención')
    if re.search(r'\b\d+\b',text) or re.search(r'\b(tres|cinco|dos|three|five|two)\b',low):score+=0.8;reasons.append('estructura/lista')
    first=low[:90]
    if any(first.startswith(connector) for connector in CONNECTOR_STARTS):score-=0.8;reasons.append('inicio dependiente')
    if len(text.split())>=5:score+=0.25
    return score,reasons


def _closure(text:str)->tuple[float,list[str]]:
    low=text.lower().strip();score=0.0;reasons=[]
    if text.rstrip().endswith(('.', '!', '?')):score+=1.0;reasons.append('cierre completo')
    hits=sum(1 for word in ACTION_WORDS if re.search(rf'\b{re.escape(word)}\b',low))
    if hits:score+=min(1.8,0.6*hits);reasons.append('acción/CTA')
    if any(phrase in low[-140:] for phrase in ('la clave','en resumen','por eso','resultado','conclusión','conclusion','that is why','the key','in short')):score+=0.9;reasons.append('remate/conclusión')
    return score,reasons


def _tone(text:str)->str:
    low=text.lower()
    action=sum(1 for word in ACTION_WORDS if re.search(rf'\b{re.escape(word)}\b',low))
    story=sum(1 for word in STORY_WORDS if re.search(rf'\b{re.escape(word)}\b',low))
    edu=sum(1 for word in EDU_WORDS if re.search(rf'\b{re.escape(word)}\b',low))
    if '?' in text and max(action,story,edu)==0:return 'provocativo'
    if action>=max(story,edu) and action:return 'accionable'
    if story>edu:return 'narrativo'
    return 'educativo'


def _duration_fit(duration:float,mode:str,target:float|None,minimum:float,maximum:float)->float:
    if mode=='objective':
        desired=float(target if target is not None else (minimum+maximum)/2)
        return max(0.0,1.0-abs(duration-desired)/max(desired,1.0))*2.2
    midpoint=(minimum+maximum)/2
    half=max((maximum-minimum)/2,1.0)
    return max(0.0,1.0-abs(duration-midpoint)/half)*0.55


def _candidate(rows:list[NarrativeSegment],i:int,j:int,mode:str,target:float|None,minimum:float,maximum:float)->NarrativeClip|None:
    start=rows[i].start;end=rows[j].end;duration=end-start
    if duration<minimum or duration>maximum:return None
    text=_clean(' '.join(row.text for row in rows[i:j+1]));hook,hook_reasons=_hook(rows[i].text);closure,closure_reasons=_closure(rows[j].text);fit=_duration_fit(duration,mode,target,minimum,maximum)
    word_count=len(text.split());density=min(1.2,word_count/55.0)
    boundary=0.55 if rows[j].text.rstrip().endswith(('.', '!', '?')) else -0.25
    standalone=0.35 if not rows[i].text.lower().startswith(CONNECTOR_STARTS) else -0.35
    score=hook+closure+fit+density+boundary+standalone
    reasons=hook_reasons+closure_reasons
    if fit>=1.4:reasons.append('duración objetivo')
    elif mode=='natural' and boundary>0:reasons.append('unidad narrativa')
    return NarrativeClip(start,end,text,round(score,4),_tone(text),round(hook,3),round(closure,3),round(fit,3),list(dict.fromkeys(reasons)))


def generate_candidates(segments,*,mode:str='natural',target_duration:float|None=None,min_duration:float=15,max_duration:float=75)->list[NarrativeClip]:
    mode=str(mode or 'natural').lower()
    if mode not in {'natural','objective'}:raise ValueError('clipper mode must be natural or objective')
    minimum=float(min_duration);maximum=float(max_duration)
    if minimum<=0 or maximum<=minimum:raise ValueError('invalid clip duration bounds')
    if target_duration is not None and not minimum<=float(target_duration)<=maximum:raise ValueError('target duration must stay inside min/max bounds')
    rows=_valid_segments(segments);candidates=[]
    for i in range(len(rows)):
        for j in range(i,len(rows)):
            duration=rows[j].end-rows[i].start
            if duration>maximum:break
            candidate=_candidate(rows,i,j,mode,target_duration,minimum,maximum)
            if candidate:candidates.append(candidate)
    candidates.sort(key=lambda row:(-row.score,row.start,row.end))
    return candidates


def select_narrative_clips(segments,target_count:int=3,*,mode:str='natural',target_duration:float|None=None,min_duration:float=15,max_duration:float=75)->list[NarrativeClip]:
    count=int(target_count)
    if count<1 or count>50:raise ValueError('target_count must be between 1 and 50')
    candidates=generate_candidates(segments,mode=mode,target_duration=target_duration,min_duration=min_duration,max_duration=max_duration)
    selected=[]
    for row in candidates:
        if any(not (row.end<=chosen.start or row.start>=chosen.end) for chosen in selected):continue
        selected.append(row)
        if len(selected)>=count:break
    selected.sort(key=lambda row:row.start)
    return selected
