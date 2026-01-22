import { Card } from './ui/card'

export function Banner() {
  return (
    <Card className="w-full p-6 mb-6 bg-gradient-to-r from-amber-700 via-orange-600 to-amber-800 text-white border-none shadow-lg">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Welcome to the Contoso Resort and Spa!</h1>
        <p className="text-sm opacity-90">Your intelligent assistant is ready to help make your experience unforgettable.</p>
      </div>
    </Card>
  )
}
