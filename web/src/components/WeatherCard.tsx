import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface WeatherCardProps {
  location: string
  temperature?: number
  temperatureC?: number
  condition?: string
  conditions?: string
  humidity?: number
  humidityPct?: number
  windKph?: number
  source?: string
}

export function WeatherCard({ 
  location, 
  temperature, 
  temperatureC, 
  condition, 
  conditions,
  humidity, 
  humidityPct,
  windKph,
  source 
}: WeatherCardProps) {
  // Support both property name formats
  const temp = temperature ?? temperatureC
  const tempF = temp ? Math.round(temp * 9/5 + 32) : null
  const cond = condition ?? conditions
  const hum = humidity ?? humidityPct
  
  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Weather in {location}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {tempF && <div className="text-4xl font-bold">{tempF}°F</div>}
          {temp && <div className="text-sm text-muted-foreground">{temp}°C</div>}
          {cond && <div className="text-lg text-muted-foreground">{cond}</div>}
          {hum && <div className="text-sm">Humidity: {hum}%</div>}
          {windKph && <div className="text-sm">Wind: {windKph} km/h</div>}
          {source && <div className="text-xs text-muted-foreground mt-2">{source}</div>}
        </div>
      </CardContent>
    </Card>
  )
}