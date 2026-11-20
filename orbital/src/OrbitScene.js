import React, { memo, useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, Platform, Pressable, View } from 'react-native';
import Svg, { Circle, Defs, Path, RadialGradient, Rect, Stop } from 'react-native-svg';
import { worlds } from './market';
import { Button, C, Dot, Icon, Planet, row, statusColor, statusName, T } from './ui';

const turn=2*Math.PI;
const steps=Array.from({length:97},(_,i)=>i/96);
function position(w,h,r,angle) {
  const x=r*Math.cos(angle);
  const orbitHeight=Math.max(60,h-155);
  return {x:w*.5+(w-24)*x,y:h*.51+orbitHeight*(r*.88*Math.sin(angle)-.22*x)};
}
function orbitPath(w,h,r) {
  return steps.map((t,i)=>{const p=position(w,h,r,t*turn);return (i?'L':'M')+p.x.toFixed(2)+' '+p.y.toFixed(2);}).join(' ')+'Z';
}
const stars=Array.from({length:195},(_,i)=>{
  const frac=n=>n-Math.floor(n);
  return [frac(Math.sin(i*121.73+1)*43758),frac(Math.sin(i*54.31+5)*21919),i%13===0?1.15:.35+(i%5)*.10];
});
const Sky=memo(function Sky({w,h}) {
  return <Svg width={w} height={h} style={{position:'absolute'}} pointerEvents="none">
    <Defs>
      <RadialGradient id="sunlight"><Stop offset="0" stopColor="#ffd094" stopOpacity=".40"/><Stop offset=".3" stopColor="#c38b45" stopOpacity=".18"/><Stop offset="1" stopColor="#c38b45" stopOpacity="0"/></RadialGradient>
    </Defs>
    <Rect width="100%" height="100%" fill="#07101b" opacity=".25"/>
    {stars.map(([x,y,r],i)=><Circle key={i} cx={x*w} cy={y*h} r={r} fill={i%9===0?'#ebd1ab':'#c3d4e9'} opacity={.22+(i%6)*.09}/>)}
    {worlds.map((p,i)=><Path key={p.s} d={orbitPath(w,h,p.r)} stroke={i%2?'#435566':'#344654'} opacity={.53} strokeWidth={.85} fill="none"/>)}
    <Circle cx={w*.5} cy={h*.51} r={Math.min(w*.23,h*.38)} fill="url(#sunlight)"/>
  </Svg>;
});

const Body=memo(function Body({w,h,planet,phase,alert,selected,onInspect,onLeave,onSelect}) {
  const size=planet.size*Math.max(.66,Math.min(1.6,w/760,h/420)), width=Math.max(50,size+8);
  const travel=useMemo(()=>{
    const positions=steps.map(t=>position(w,h,planet.r,planet.a+turn*t));
    return ['x','y'].map(k=>phase.interpolate({inputRange:steps,outputRange:positions.map(p=>p[k])}));
  },[w,h,planet,phase]);
  return <Animated.View pointerEvents="box-none" style={{position:'absolute',left:-width/2,top:-size/2,width,alignItems:'center',zIndex:selected?4:2,transform:[{translateX:travel[0]},{translateY:travel[1]}]}}>
    <Pressable accessibilityRole="button" accessibilityLabel={planet.s+', '+statusName(alert)} accessibilityState={{selected}} testID={'planet-'+planet.s}
      onHoverIn={e=>onInspect(planet.s,e)} onHoverOut={()=>onLeave(planet.s)}
      onFocus={e=>onInspect(planet.s,e)} onBlur={()=>onLeave(planet.s)}
      onPress={e=>onSelect(planet.s,e)}
      style={{alignItems:'center',minWidth:44,minHeight:44}}>
      <View style={{width:size,height:size,alignItems:'center',justifyContent:'center'}}>
        {alert===true&&<View pointerEvents="none" style={{position:'absolute',width:size*1.48,height:size*1.48}}>
          <Svg width="100%" height="100%"><Defs><RadialGradient id={'halo'+planet.s}><Stop offset=".44" stopColor={C.alarm} stopOpacity=".8"/><Stop offset=".64" stopColor="#ff7d45" stopOpacity=".34"/><Stop offset="1" stopColor="#ff7d45" stopOpacity="0"/></RadialGradient></Defs><Rect width="100%" height="100%" fill={'url(#halo'+planet.s+')'}/></Svg>
        </View>}
        <Planet tile={planet.tile} size={size}/>
        {selected&&<View style={{position:'absolute',width:size*1.02,height:size*1.02,borderRadius:size,borderWidth:1,borderColor:alert?C.alarm:'#d3dfe0'}}/>}
      </View>
      <View style={[row,{gap:4,marginTop:2,paddingHorizontal:5,paddingVertical:2,borderRadius:4,backgroundColor:'#0b1522dc'}]}>
        <Dot color={statusColor(alert)} size={4}/><T size={w<480?10:12} weight="650">{planet.s}</T>
      </View>
    </Pressable>
  </Animated.View>;
});
export function OrbitScene({stats,selected,onSelect,onInspect,onLeave,compact}) {
  const [{width,height},setSize]=useState({width:0,height:0}),[rotating,setRotating]=useState(true);
  const phase=useRef(new Animated.Value(0)).current, at=useRef(0);
  useEffect(()=>{
    if(Platform.OS==='web'){
      const query=window.matchMedia('(prefers-reduced-motion: reduce)');
      if(query.matches)setRotating(false);
      return;
    }
    AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(v)setRotating(false);});
  },[]);
  useEffect(()=>{
    if(!rotating||selected)return;
    let live=true,animation;
    function run(start) {
      phase.setValue(start);
      animation=Animated.timing(phase,{toValue:1,duration:Math.max(50,(1-start)*230000),easing:Easing.linear,useNativeDriver:Platform.OS!=='web',isInteraction:false});
      animation.start(({finished})=>{if(live&&finished){at.current=0;run(0);}});
    }
    run(at.current);
    return ()=>{live=false;phase.stopAnimation(value=>{at.current=value%1;});};
  },[phase,rotating,selected]);
  const sun=Math.min(160,height*.22,Math.max(68,width*.13));
  return <View onLayout={e=>{
    const {width:w,height:h}=e.nativeEvent.layout;
    setSize(prev=>prev.width===w&&prev.height===h?prev:{width:w,height:h});
  }} style={{flex:1,overflow:'hidden',backgroundColor:'#091221'}}>
    <Image source={require('../assets/galaxy.png')} resizeMode="cover" accessible={false}
      style={{position:'absolute',left:0,top:0,width:'100%',height:'100%'}}/>
    {width>0&&<>
      <Sky w={width} h={height}/>
      <View pointerEvents="none" style={{position:'absolute',left:(width-sun)/2,top:height*.51-sun/2,alignItems:'center',width:sun}}>
        <Planet tile={4} size={sun}/><T size={9} color={C.gold} weight="650" style={{letterSpacing:1.4}}>MẶT TRỜI</T>
      </View>
      {worlds.map(planet=><Body key={planet.s} w={width} h={height} planet={planet} phase={phase} alert={stats[planet.s].alert} selected={planet.s===selected} onSelect={onSelect} onInspect={onInspect} onLeave={onLeave}/>)}
    </>}
    <Button label={rotating?'Tạm dừng quỹ đạo':'Cho hành tinh quay'} selected={!rotating} onPress={()=>setRotating(v=>!v)} style={{position:'absolute',right:compact?13:24,top:compact?66:82,padding:9,zIndex:5,backgroundColor:'#0d1825b0',borderWidth:1,borderColor:'#95afc52f',borderRadius:20}}>
      <Icon name="orbit" size={17} color={rotating?C.gold:C.muted}/>
    </Button>
  </View>;
}
