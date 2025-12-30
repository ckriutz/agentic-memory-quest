import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface AppointmentCardProps {
  doctorName?: string
  specialty?: string
  appointmentDate?: string
  appointmentTime?: string
  aboutDoctor?: string
  imageUrl?: string
  className?: string
}

export function AppointmentCard({
  doctorName = "Dr. Maria Waston",
  specialty = "Cardio Specialist",
  appointmentDate = "January 15, 2026",
  appointmentTime = "10:30 AM",
  aboutDoctor = "Dr. Maria Waston is the top most Cardiologist specialist in Nanyang Hospotalat London. She is available for private consultation.",
  imageUrl = "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=400&h=400&fit=crop",
  className
}: AppointmentCardProps) {
  return (
    <Card className={`w-full overflow-hidden ${className || ''}`}>
      <CardHeader className="text-center pb-4">
        <CardTitle className="text-2xl font-semibold text-gray-700">
          Next Appointment
        </CardTitle>
      </CardHeader>
      
      <CardContent className="space-y-6">
        {/* Doctor Profile Section */}
        <div className="flex flex-col items-center space-y-3">
          <img
            src={imageUrl}
            alt={doctorName}
            className="w-24 h-24 rounded-full object-cover border-4 border-blue-100"
          />
          
          <div className="text-center">
            <h3 className="text-xl font-semibold text-gray-800">{doctorName}</h3>
            <p className="text-sm text-gray-500 flex items-center justify-center gap-1">
              <span className="text-pink-400">❤</span>
              {specialty}
            </p>
          </div>
        </div>

        {/* Appointment Date & Time */}
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="text-center">
              <div className="text-lg font-bold text-blue-600">
                {appointmentDate.split(',')[0].split(' ')[1]}
              </div>
              <div className="text-xs text-gray-600">
                {appointmentDate.split(' ')[0]} {appointmentDate.split(',')[1]?.trim() || new Date().getFullYear()}
              </div>
            </div>
            
            <div className="text-center border-l border-blue-200">
              <div className="text-lg font-bold text-green-600">
                {appointmentTime}
              </div>
            </div>
          </div>
        </div>

        {/* About Doctor Section */}
        <div className="space-y-2">
          <h4 className="text-lg font-semibold text-gray-800">About Doctor</h4>
          <p className="text-sm text-gray-600 leading-relaxed">
            {aboutDoctor}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
