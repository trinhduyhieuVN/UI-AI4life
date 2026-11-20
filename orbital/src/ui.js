import React from 'react';
import { Image, Platform, Pressable, Text, View } from 'react-native';
import Svg, { Circle, Ellipse, Path } from 'react-native-svg';

export const C={bg:'#070d18',panel:'#0c1522',line:'#223142',muted:'#98a8bc',dim:'#718498',white:'#edf3f9',mint:'#7edbb9',gold:'#ecc079',alarm:'#ff996d'};
export const row={flexDirection:'row',alignItems:'center'};
export const mono=Platform.select({web:'ui-monospace, Consolas, monospace',ios:'Menlo',android:'monospace'});
export function T({children,size=14,color=C.white,weight='400',style,...props}) {
  return <Text {...props} style={[{fontFamily:Platform.OS==='web'?'Inter, system-ui, sans-serif':undefined,color,fontSize:size,fontWeight:weight},style]}>{children}</Text>;
}
export function Caption({children,style}) {return <T size={10} color={C.muted} weight="700" style={[{letterSpacing:1.35},style]}>{children}</T>;}
export function Dot({color,size=6}) {return <View style={{width:size,height:size,borderRadius:size,backgroundColor:color}}/>;}
export function Planet({tile,size}) {
  return <View pointerEvents="none" style={{width:size,height:size,overflow:'hidden'}}>
    <Image resizeMethod="scale" resizeMode="stretch" source={require('../assets/worlds.png')} style={{position:'absolute',width:size*3,height:size*3,left:-(tile%3)*size,top:-Math.floor(tile/3)*size}}/>
  </View>;
}
const paths={play:'M8 5l11 7-11 7z',pause:'M8 5v14 M16 5v14',calendar:'M4 8h16 M7 3v4 M17 3v4 M4 5h16v16H4z',chevron:'m7 10 5 5 5-5',arrow:'M7 17 18 6 M8 6h10v10',left:'m14 6-6 6 6 6',right:'m10 6 6 6-6 6',close:'M6 6l12 12 M18 6 6 18',news:'M4 5h16v14H4z M7 9h10 M7 12h10 M7 15h6',wave:'M2 14h4l3-8 4 13 3-8 2 3h4'};
export function Icon({name,size=18,color=C.muted}) {
  return <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">{name==='orbit'?<>
    <Circle cx="12" cy="12" r="7.7" stroke={color} strokeWidth="1.4"/><Ellipse cx="12" cy="12" rx="11.4" ry="4" rotation="-33" origin="12,12" stroke={color} strokeWidth="1.3"/><Circle cx="18" cy="6" r="1.7" fill={color}/>
    </>:<Path d={name==='bell'?'M4.5 17c1.6-1.9 2-3.1 2-7a5.5 5.5 0 0 1 11 0c0 3.9.4 5.1 2 7H4.5z M9.8 20a2.6 2.6 0 0 0 4.4 0 M12 3v1.4':paths[name]} stroke={color} fill={name==='play'?color:'none'} strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"/>}</Svg>;
}
export function Button({label,onPress,children,style,selected,disabled,testID}) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{selected,disabled}} disabled={disabled} testID={testID} onPress={onPress}
    style={({pressed,hovered})=>[row,{justifyContent:'center',gap:7,borderRadius:8,opacity:disabled?.46:pressed?.74:1},hovered&&{backgroundColor:'#1c2938'},style]}>{children}</Pressable>;
}
export const statusColor=a=>a===null?C.dim:a?C.alarm:C.mint;
export const statusName=a=>a===null?'Chưa có dữ liệu':a?'Bất thường':'Bình thường';
