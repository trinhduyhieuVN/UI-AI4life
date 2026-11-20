import React, {memo, useCallback, useEffect, useReducer, useRef, useState} from 'react';
import {AccessibilityInfo, Animated, Easing, Linking, Platform, Pressable, View} from 'react-native';
import {C, mono, row, T} from './ui';
import {useHeadlines} from './News';

function useReducedMotion() {
  const [reduced,setReduced] = useState(true);
  useEffect(() => {
    if (Platform.OS === 'web') {
      const media = window.matchMedia('(prefers-reduced-motion: reduce)');
      const sync = () => setReduced(media.matches);
      sync();
      media.addEventListener('change',sync);
      return () => media.removeEventListener('change',sync);
    }
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().then(value => {if (active) setReduced(value);});
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged',setReduced);
    return () => {active=false; sub.remove();};
  },[]);
  return reduced;
}

const GAP = 24;
const SPEED = 52;

function Story({item,onMeasure,onFocusChange,stationary=false}) {
  const [failed,setFailed]=useState(false);
  const open=async()=>{try {await Linking.openURL(item.url);} catch {setFailed(true);}};
  return <Pressable testID="ticker-article" accessibilityRole="link" accessibilityLabel={item.symbols.join(', ')+' · '+item.title}
    onPress={open} onFocus={()=>onFocusChange?.(true)} onBlur={()=>onFocusChange?.(false)}
    onLayout={onMeasure ? e=>onMeasure(e.nativeEvent.layout.width) : undefined}
    style={{height:36,justifyContent:'center',flexShrink:stationary?1:0}}>
    <T size={13} numberOfLines={1}><T size={11} color={C.gold} weight="700" style={{fontFamily:mono}}>{item.symbols.join('·')}</T>
      {'   '+(failed?'Chưa mở được bài gốc':item.title)}</T>
  </Pressable>;
}

// At each handoff the incoming story starts at x=0 in the next strip.
// Its predecessors keep their exact spacing as they travel toward the right edge.
function MovingStrip({item,history,paused,onFocusChange,advance}) {
  const [width,setWidth]=useState(0);
  const distance=width+GAP;
  const duration=distance/SPEED*1000;
  const track=useRef(null);
  const player=useRef(null);
  const progress=useRef(new Animated.Value(0)).current;
  const saved=useRef(0);

  useEffect(()=>{
    if (!width || Platform.OS!=='web') return;
    const animation=track.current.animate([{transform:'translateX(0px)'},{transform:'translateX('+distance+'px)'}],
      {duration,easing:'linear',fill:'both'});
    animation.pause();
    animation.onfinish=()=>advance(width);
    player.current=animation;
    return ()=>{animation.onfinish=null;animation.cancel();player.current=null;};
  },[width,distance,duration,advance]);

  useEffect(()=>{
    if (!width) return;
    if (Platform.OS==='web') {
      if (paused) player.current?.pause(); else player.current?.play();
      return;
    }
    if (paused) return;
    const movement=Animated.timing(progress,{toValue:1,duration:duration*(1-saved.current),
      easing:Easing.linear,useNativeDriver:true,isInteraction:false});
    movement.start(({finished})=>{if (finished) advance(width);});
    return ()=>progress.stopAnimation(value=>{saved.current=value;});
  },[width,paused,duration,progress,advance]);

  const Track=Platform.OS==='web'?View:Animated.View;
  const transform=Platform.OS==='web'?undefined:[{translateX:progress.interpolate({inputRange:[0,1],outputRange:[0,distance]})}];
  return <Track ref={track} testID="ticker-track" pointerEvents="box-none" style={{position:'absolute',left:0,top:0,height:36,width:'100%',transform}}>
    <View pointerEvents="box-none" style={{position:'absolute',right:'100%',width:8192,paddingRight:GAP,alignItems:'flex-end'}}>
      <Story item={item} onMeasure={setWidth} onFocusChange={onFocusChange}/>
    </View>
    <View pointerEvents="box-none" style={[row,{position:'absolute',left:0,gap:GAP,width:8192}]}>
      {history.map(story=><Story key={story.sequence} item={story.item} onFocusChange={onFocusChange}/>)}
    </View>
  </Track>;
}

const emptyQueue = {items:[], pending:[], current:null, sequence:0, history:[]};

function updateQueue(state, action) {
  if (action.type==='snapshot') {
    const items=action.items;
    if (!items.length) return emptyQueue;
    if (!state.current) return {...emptyQueue,items,current:items[0]};
    const previousUrls=new Set(state.items.map(item=>item.url));
    const pendingUrls=new Set(state.pending.map(item=>item.url));
    const pending=items.filter(item=>item.url!==state.current.url &&
      (!previousUrls.has(item.url) || pendingUrls.has(item.url)));
    return {...state,items,pending};
  }
  if (!state.items.length) return state;
  const rotation=state.items.slice(0,8);
  const index=rotation.findIndex(item=>item.url===state.current.url);
  const current=state.pending[0] || rotation[(index+1)%rotation.length];
  const history=[];
  let occupied=0;
  for (const story of [{item:state.current,width:action.width,sequence:state.sequence},...state.history]) {
    if (occupied>=action.laneWidth) break;
    history.push(story);
    occupied+=story.width+GAP;
  }
  return {...state,current,history,pending:state.pending.slice(1),sequence:state.sequence+1};
}

export const NewsTicker=memo(function NewsTicker() {
  const {data,offline}=useHeadlines();
  const [queue,dispatch]=useReducer(updateQueue,emptyQueue);
  const reduced=useReducedMotion();
  useEffect(()=>{
    if (data?.items) dispatch({type:'snapshot',items:data.items});
  },[data]);
  const lane=useRef(0);
  const [hover,setHover]=useState(false);
  const [focus,setFocus]=useState(false);
  const advance=useCallback(width=>dispatch({type:'next',width,laneWidth:lane.current}),[]);
  const failed=offline || (data?.failed?.length===6 && data?.stream!=='live');
  const empty=failed?'Tạm mất nguồn tin':data?.checked?'Chưa có tin mới':'Đang tải tin…';
  return <View testID="toolbar-news" onLayout={e=>{lane.current=e.nativeEvent.layout.width;}}
    onPointerEnter={e=>{if(e.nativeEvent.pointerType==='mouse') setHover(true);}} onPointerLeave={()=>setHover(false)}
    style={[row,{width:'100%',minWidth:0,height:36,overflow:'hidden'}]}>
    {queue.current ? (reduced ? <Story item={queue.items[0]} stationary/> :
      <MovingStrip key={queue.sequence} item={queue.current} history={queue.history} advance={advance} paused={hover||focus} onFocusChange={setFocus}/>) :
      <T size={12} color={C.muted} style={{flex:1}}>{empty}</T>}
  </View>;
});
